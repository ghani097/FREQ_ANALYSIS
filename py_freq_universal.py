"""
Universal EEG Frequency Analysis Engine
========================================
Supports any number of groups (2, 3, ...) and auto-detects all session pairs.

Key differences vs py_analyzer.py / py_visualizer.py:
  - Loads ALL sessions (not just pre/post)
  - Builds all ordered session pairs automatically (Pre->During, Pre->Post, During->Post, ...)
  - Runs within-group tests for every group
  - Runs between-group pairwise tests for every pair of groups
  - Visualization adapts dynamically to N groups

Usage:
    python py_freq_universal.py --data "E:\\ANN_DATA\\Ann Preprocessed GEDAI\\EC" --fast
    python py_freq_universal.py --data "E:\\ANN_DATA\\Ann Preprocessed GEDAI\\EC"
"""

import os
import sys
import warnings
from itertools import combinations, product
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import gridspec
import mne
from mne.viz import plot_topomap

from py_analyzer import FrequencyAnalyzer
from py_visualizer import ResultVisualizer
from py_config import FREQUENCY_BANDS, DEFAULT_PARAMS, PUBLICATION_PARAMS


# ---------------------------------------------------------------------------
# Universal Analyzer
# ---------------------------------------------------------------------------

class UniversalFrequencyAnalyzer(FrequencyAnalyzer):
    """
    Extends FrequencyAnalyzer to handle N groups and all session pairs.

    Overrides:
        _load_all_data()      - loads ALL sessions, not filtered by role
        run_analysis()        - builds all session pairs, drives N-group pipeline
    Adds:
        _build_session_pairs()     - auto-detect or config-based session ordering
        _analyze_band_universal()  - within + pairwise between-group tests per band
        _map_sig_to_plot()         - helper: common-channel mask -> plot-channel mask
        _print_statistics_universal() - progress logging for N-group results
    """

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run_analysis(self) -> Dict:
        self.progress("=== Starting Universal EEG Frequency Analysis ===")

        # Load ALL groups x ALL sessions
        group_data = self._load_all_data()
        if not group_data:
            raise ValueError("No data loaded.")

        groups = list(group_data.keys())
        # All sessions present across any group
        all_sessions = sorted({s for g in groups for s in group_data[g].keys()})

        session_pairs = self._build_session_pairs(all_sessions)

        self.progress(f"Groups   : {groups}")
        self.progress(f"Sessions : {all_sessions}")
        self.progress(f"Pairs    : {[f'{a}->{b}' for a, b in session_pairs]}")

        all_results: Dict[str, Dict] = {}

        for session_1, session_2 in session_pairs:
            comparison_name = f"{session_2}_vs_{session_1}"
            self.progress(f"\n{'='*60}")
            self.progress(f"Session pair: {session_1} -> {session_2}")
            self.progress(f"{'='*60}")

            # Collect matched data for every group
            group_session_data: Dict[str, Tuple[List, List]] = {}
            all_pair_data: List = []
            skip = False

            for grp in groups:
                pre_list, post_list = self._get_matched_session_data(
                    group_data[grp], session_1, session_2)
                if not pre_list or not post_list:
                    self.progress(f"  WARNING: No matched data for {grp} "
                                  f"({session_1}/{session_2}) — skipping pair")
                    skip = True
                    break
                group_session_data[grp] = (pre_list, post_list)
                all_pair_data.extend(pre_list + post_list)

            if skip:
                all_results[comparison_name] = {}
                continue

            # Channel alignment across ALL groups simultaneously
            common_channels, common_info, excluded, plot_channels, plot_info = \
                self._align_channels_for_comparison(all_pair_data, comparison_name)

            if common_channels is None or plot_channels is None:
                self.progress("  WARNING: Insufficient common channels — skipping pair")
                all_results[comparison_name] = {}
                continue

            # Remove excluded subjects from every group
            if excluded:
                for grp in groups:
                    pre_list, post_list = group_session_data[grp]
                    group_session_data[grp] = (
                        [d for d in pre_list if d['subject_id'] not in excluded],
                        [d for d in post_list if d['subject_id'] not in excluded],
                    )

            # Analyze each frequency band
            pair_results: Dict[str, Dict] = {}
            self.progress("Analyzing frequency bands...")

            for band_name, band_range in FREQUENCY_BANDS.items():
                self.progress(f"  {band_name} ({band_range[0]}-{band_range[1]} Hz)...")
                try:
                    result = self._analyze_band_universal(
                        group_session_data, groups,
                        band_name, band_range,
                        common_channels, common_info,
                        plot_channels, plot_info,
                        session_1, session_2,
                    )
                    if result is not None:
                        pair_results[band_name] = result
                        self.progress(f"    [OK] {band_name}")
                        self._print_statistics_universal(result, band_name)
                except Exception as e:
                    self.progress(f"    [FAIL] {band_name}: {e}")

            all_results[comparison_name] = pair_results

        self.progress("\n=== Universal Analysis Complete ===")
        self.results = all_results
        return all_results

    # ------------------------------------------------------------------
    # Data loading (override: load ALL sessions)
    # ------------------------------------------------------------------

    def _load_all_data(self) -> Dict:
        """Load every group × every session (ignores baseline/comparison role config)."""
        output_dir_name = Path(self.config.get("output_dir", "")).name
        exclude = [output_dir_name] if output_dir_name else []
        scan_info = self.loader.scan_directory(exclude_dirs=exclude)

        self.progress(f"  Found {scan_info['total_files']} .set files")
        self.progress(f"  Groups  : {', '.join(scan_info['groups'])}")
        self.progress(f"  Sessions: {', '.join(scan_info['sessions'])}")

        resample_rate = self.config.get('resample_rate', None)
        ignore_epochs = self.config.get('ignore_epochs', True)
        max_epochs = self.config.get('max_epochs', None) or None
        apply_rejection = self.config.get('apply_epoch_rejection', True)

        group_data: Dict = {}

        for group in scan_info['groups']:
            group_data[group] = {}
            for session in scan_info['sessions']:
                session_path = self.loader.root_dir / group / session
                if not session_path.exists():
                    continue

                set_files = sorted(session_path.glob('*.set'))
                subjects = [f.stem for f in set_files]
                if not subjects:
                    self.progress(f"  WARNING: No .set files in {group}/{session}")
                    continue

                self.progress(f"  Loading {group}/{session}: {len(subjects)} subjects...")
                group_data[group][session] = {'subjects': subjects, 'data': []}

                for subj in subjects:
                    try:
                        filepath = session_path / f"{subj}.set"
                        raw = self.loader.load_set_file(
                            filepath,
                            resample_rate=resample_rate,
                            ignore_epochs=ignore_epochs,
                            max_epochs=max_epochs,
                            apply_epoch_rejection=apply_rejection,
                        )
                        if self.detected_sfreq is None:
                            self.detected_sfreq = raw.info['sfreq']
                            self.progress(f"  Detected sfreq: {self.detected_sfreq} Hz")

                        psd = self._compute_psd(raw)
                        if psd is not None:
                            psd['subject_id'] = subj
                            group_data[group][session]['data'].append(psd)

                    except Exception as e:
                        self.progress(f"    Warning: {subj}: {e}")

                n_ok = len(group_data[group][session]['data'])
                self.progress(f"    Loaded {n_ok}/{len(subjects)}")

        return group_data

    # ------------------------------------------------------------------
    # Session-pair detection
    # ------------------------------------------------------------------

    # Known temporal ordering for common session naming conventions
    _SESSION_ORDER_KEYS = [
        ('pre', 0), ('baseline', 0), ('rest', 0),
        ('during', 1), ('intra', 1), ('mid', 1), ('stim', 1), ('active', 1),
        ('post', 2),
        ('follow', 3), ('fu', 3),
        ('w1', 4), ('w2', 5), ('w4', 6), ('w6', 7), ('w8', 8),
        ('m1', 10), ('m3', 12), ('m6', 15), ('m12', 18),
    ]

    def _session_rank(self, s: str) -> Tuple[int, str]:
        sl = s.lower()
        for key, rank in self._SESSION_ORDER_KEYS:
            if key in sl:
                return (rank, sl)
        return (99, sl)

    def _build_session_pairs(self, sessions: List[str]) -> List[Tuple[str, str]]:
        """Return ordered (session_1, session_2) pairs to analyze.

        Priority:
        1. If both baseline_sessions and comparison_sessions are in config -> cartesian product.
        2. Otherwise -> auto-detect temporal order and return all forward pairs.
        """
        baseline = self.config.get('baseline_sessions', [])
        comparison = self.config.get('comparison_sessions', [])

        if baseline and comparison:
            self.progress("Session pairs: using config (baseline x comparison)")
            return list(product(baseline, comparison))

        # Auto-detect
        sorted_sessions = sorted(sessions, key=self._session_rank)
        self.progress(f"Session order (auto-detected): {sorted_sessions}")
        pairs = [
            (sorted_sessions[i], sorted_sessions[j])
            for i in range(len(sorted_sessions))
            for j in range(i + 1, len(sorted_sessions))
        ]
        return pairs

    # ------------------------------------------------------------------
    # Universal band analysis
    # ------------------------------------------------------------------

    def _analyze_band_universal(
        self,
        group_session_data: Dict[str, Tuple[List, List]],
        groups: List[str],
        band_name: str,
        band_range: Tuple[float, float],
        common_channels: List[str],
        common_info,
        plot_channels: List[str],
        plot_info,
        session_1: str,
        session_2: str,
    ) -> Optional[Dict]:
        """Compute band-power differences and run all tests for N groups.

        Returns a result dict with:
          - within_group[grp]          : one-sample cluster/t-test per group
          - between_group[pair_key]    : two-sample cluster/t-test per group pair
          - ga_diffs[grp]              : grand-average difference on plot_channels
          - within_group_masks[grp]    : boolean mask on plot_channels
        """
        # --- Per-group band-power differences (on common_channels for stats) ---
        group_diffs: Dict[str, np.ndarray] = {}
        group_plot_ga: Dict[str, np.ndarray] = {}

        for grp in groups:
            pre_list, post_list = group_session_data[grp]

            diff = self._compute_band_differences(
                pre_list, post_list, band_range, common_channels)
            if diff is None or len(diff) == 0:
                self.progress(f"    [SKIP] {grp}: no matched subjects")
                return None
            group_diffs[grp] = diff  # shape (n_subj, n_common)

            # Grand-average on union (plot) channels for topomap display
            plot_diff = self._compute_band_differences(
                pre_list, post_list, band_range, plot_channels, allow_missing=True)
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                group_plot_ga[grp] = np.nanmean(plot_diff, axis=0)

        n_subjects = {grp: len(v) for grp, v in group_diffs.items()}
        self.progress("    n subjects: " +
                      ", ".join(f"{g}={n}" for g, n in n_subjects.items()))

        # --- Within-group tests (one-sample: did session_1->session_2 change?) ---
        within_group: Dict[str, Dict] = {}
        for grp in groups:
            self.progress(f"    Within-group [{grp}]...")
            within_group[grp] = self._run_within_group_test(
                group_diffs[grp], info=common_info)

        # --- Between-group tests (two-sample: is change different between groups?) ---
        between_group: Dict[str, Dict] = {}
        for grp_a, grp_b in combinations(groups, 2):
            pair_key = f"{grp_a} vs {grp_b}"
            self.progress(f"    Between-group [{pair_key}]...")

            stat = self._run_cluster_test(
                group_diffs[grp_a], group_diffs[grp_b], info=common_info)

            # Grand-average difference for topomap
            ga_diff = group_plot_ga[grp_a] - group_plot_ga[grp_b]
            sig_mask_plot = self._map_sig_to_plot(
                stat.get('sig_mask'), common_channels, plot_channels)

            between_group[pair_key] = {
                'groups': (grp_a, grp_b),
                'statistics': stat,
                'ga_diff': ga_diff,
                'sig_mask_plot': sig_mask_plot,
            }

        # --- Map within-group sig masks to plot channels ---
        within_group_masks: Dict[str, np.ndarray] = {}
        for grp in groups:
            mask = within_group[grp].get('sig_mask')
            within_group_masks[grp] = self._map_sig_to_plot(
                mask, common_channels, plot_channels)

        # --- Diagnostic: check groups differ ---
        for grp_a, grp_b in combinations(groups, 2):
            diff_ab = np.abs(group_plot_ga[grp_a] - group_plot_ga[grp_b])
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                mean_d = float(np.nanmean(diff_ab))
            if np.isnan(mean_d):
                self.progress(f"    [WARNING] {grp_a} vs {grp_b}: difference is all NaN")
            elif mean_d < 1e-10:
                self.progress(f"    [WARNING] {grp_a} vs {grp_b}: groups appear IDENTICAL")
            else:
                self.progress(f"    [OK] {grp_a} vs {grp_b}: mean diff = {mean_d:.2e}")

        return {
            'band_name': band_name,
            'band_range': band_range,
            'session_1': session_1,
            'session_2': session_2,
            'groups': groups,
            'n_subjects': n_subjects,
            'ga_diffs': group_plot_ga,           # grp -> (n_plot_ch,) array
            'within_group': within_group,         # grp -> stat result dict
            'between_group': between_group,       # "A vs B" -> {statistics, ga_diff, ...}
            'within_group_masks': within_group_masks,  # grp -> bool array on plot_channels
            'ch_names': plot_channels,
            'info': plot_info,
            'common_ch_names': common_channels,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_sig_to_plot(
        sig_mask: Optional[np.ndarray],
        common_channels: List[str],
        plot_channels: List[str],
    ) -> np.ndarray:
        """Map a significance mask on common_channels to plot_channels."""
        out = np.zeros(len(plot_channels), dtype=bool)
        if sig_mask is not None and np.any(sig_mask):
            common_idx = {ch: i for i, ch in enumerate(common_channels)}
            for i, ch in enumerate(plot_channels):
                idx = common_idx.get(ch)
                if idx is not None and sig_mask[idx]:
                    out[i] = True
        return out

    def _print_statistics_universal(self, result: Dict, band_name: str):
        """Log key p-values for all tests in a band result."""

        def _best_p(stat: Dict) -> float:
            p_pos = stat['positive_clusters'][0]['pval'] \
                if stat.get('positive_clusters') else 1.0
            p_neg = stat['negative_clusters'][0]['pval'] \
                if stat.get('negative_clusters') else 1.0
            return min(p_pos, p_neg)

        self.progress(f"    --- {band_name} p-values ---")
        for grp, stat in result['within_group'].items():
            p = _best_p(stat)
            stars = '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else ''))
            self.progress(f"      Within {grp}: p={p:.4f}{stars}")
        for pair_key, pair_data in result['between_group'].items():
            p = _best_p(pair_data['statistics'])
            stars = '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else ''))
            self.progress(f"      Between {pair_key}: p={p:.4f}{stars}")


# ---------------------------------------------------------------------------
# Universal Visualizer
# ---------------------------------------------------------------------------

class UniversalResultVisualizer(ResultVisualizer):
    """
    Extends ResultVisualizer for N-group universal results.

    Layout conventions:
      plot_band_result : row-0 = within-group topomaps (one per group)
                         row-1 = between-group topomaps (one per pair)
      plot_summary     : rows = groups then pairs; cols = frequency bands
      plot_statistics_table : dynamic columns for N groups and all pairs
    """

    # ------------------------------------------------------------------
    # Single-band figure (2 rows × max(N_groups, N_pairs) cols)
    # ------------------------------------------------------------------

    def plot_band_result(self, result: Dict, show: bool = False,
                         comparison_name: str = '') -> str:
        """Per-band topomap figure for N groups."""
        band_name = result['band_name']
        band_range = result['band_range']
        groups = result['groups']
        session_1 = result['session_1']
        session_2 = result['session_2']
        info = result['info']
        group_pairs = list(combinations(groups, 2))

        n_groups = len(groups)
        n_pairs = len(group_pairs)
        n_cols = max(n_groups, n_pairs)
        n_rows = 2

        fig_w = max(15, 5 * n_cols)
        fig_h = 5 * n_rows + 1.5
        fig = plt.figure(figsize=(fig_w, fig_h), facecolor='white')
        prefix = f"{comparison_name} | " if comparison_name else ""
        fig.suptitle(
            f"{prefix}{band_name} Band ({band_range[0]}-{band_range[1]} Hz)",
            fontsize=14, fontweight='bold', y=0.99,
        )

        gs = gridspec.GridSpec(
            n_rows, n_cols, figure=fig,
            hspace=0.45, wspace=0.3,
            left=0.04, right=0.96, top=0.93, bottom=0.06,
        )

        sm_params = dict(
            marker='X',
            markerfacecolor=PUBLICATION_PARAMS['colors']['sig_marker'],
            markersize=16, markeredgecolor='white', markeredgewidth=2,
        )

        # --- Row 0: within-group ---
        ga_vals = [np.nan_to_num(result['ga_diffs'][g]) for g in groups]
        vmax_within = max((np.abs(v).max() for v in ga_vals), default=1.0)
        if vmax_within == 0:
            vmax_within = 1.0

        for col, grp in enumerate(groups):
            ax = fig.add_subplot(gs[0, col])
            data_plot = np.nan_to_num(result['ga_diffs'][grp])
            mask = result['within_group_masks'].get(grp)
            if mask is not None and not np.any(mask):
                mask = None

            plot_topomap(
                data_plot, info, axes=ax,
                cmap=PUBLICATION_PARAMS['colors']['cmap'],
                vlim=(-vmax_within, vmax_within),
                show=False, contours=4, sensors=True,
                mask=mask,
                mask_params=sm_params if mask is not None else None,
            )
            n = result['n_subjects'][grp]
            stat = result['within_group'][grp]
            p_best = self._best_p(stat)
            stars = self._stars(p_best)
            ax.set_title(
                f"{grp}  (n={n})\n"
                f"{session_2} - {session_1}"
                f"{('  p=' + f'{p_best:.3f}' + stars) if stars else ''}",
                fontsize=PUBLICATION_PARAMS['font']['label_size'],
            )

        # Row-0 label
        if n_groups > 0:
            fig.text(0.01, 0.72, "Within-group change",
                     va='center', rotation='vertical', fontsize=11, fontweight='bold')

        # --- Row 1: between-group ---
        for col, (grp_a, grp_b) in enumerate(group_pairs):
            pair_key = f"{grp_a} vs {grp_b}"
            pair_data = result['between_group'][pair_key]
            stat = pair_data['statistics']
            p_best = self._best_p(stat)
            stars = self._stars(p_best)

            ax = fig.add_subplot(gs[1, col])
            data_plot = np.nan_to_num(pair_data['ga_diff'])
            vmax_pair = np.abs(data_plot).max()
            if vmax_pair == 0:
                vmax_pair = 1.0

            mask = pair_data.get('sig_mask_plot')
            if mask is not None and not np.any(mask):
                mask = None

            plot_topomap(
                data_plot, info, axes=ax,
                cmap=PUBLICATION_PARAMS['colors']['cmap'],
                vlim=(-vmax_pair, vmax_pair),
                show=False, contours=4, sensors=True,
                mask=mask,
                mask_params=sm_params if mask is not None else None,
            )
            title_color = PUBLICATION_PARAMS['colors']['significant'] if stars else 'black'
            ax.set_title(
                f"{grp_a} vs {grp_b}"
                f"{('  p=' + f'{p_best:.3f}' + stars) if stars else ''}",
                fontsize=PUBLICATION_PARAMS['font']['label_size'],
                color=title_color,
                fontweight='bold' if stars else 'normal',
            )

        # Row-1 label
        if n_pairs > 0:
            fig.text(0.01, 0.26, "Between-group interaction",
                     va='center', rotation='vertical', fontsize=11, fontweight='bold')

        # Save
        prefix_file = f"{comparison_name}_" if comparison_name else ""
        output_file = self.figures_dir / f"{prefix_file}{band_name}_band.png"
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                    bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()
        return str(output_file)

    # ------------------------------------------------------------------
    # Summary figure (N_groups+N_pairs rows × N_bands cols)
    # ------------------------------------------------------------------

    def plot_summary(self, all_results: Dict, show: bool = False,
                     comparison_name: str = None) -> Optional[str]:
        """Summary topomaps: rows = groups + pairs, cols = bands."""
        band_names = list(all_results.keys())
        if not band_names:
            return None

        first = all_results[band_names[0]]
        groups = first['groups']
        group_pairs = list(combinations(groups, 2))
        session_1 = first['session_1']
        session_2 = first['session_2']

        n_rows = len(groups) + len(group_pairs)
        n_cols = len(band_names)

        fig = plt.figure(figsize=(4 * n_cols, 4 * n_rows + 1), facecolor='white')
        title = (f"Frequency Analysis Summary\n"
                 f"{comparison_name}  |  {session_2} vs {session_1}"
                 if comparison_name else
                 f"Frequency Analysis Summary  |  {session_2} vs {session_1}")
        fig.suptitle(title, fontsize=14, fontweight='bold', y=0.99)

        gs = gridspec.GridSpec(
            n_rows, n_cols, figure=fig,
            hspace=0.35, wspace=0.25,
            left=0.08, right=0.96, top=0.95, bottom=0.03,
        )

        sm_params = dict(
            marker='X',
            markerfacecolor=PUBLICATION_PARAMS['colors']['sig_marker'],
            markersize=12, markeredgecolor='white', markeredgewidth=1.5,
        )

        for col, band_name in enumerate(band_names):
            result = all_results[band_name]
            band_range = result['band_range']
            info = result['info']

            ga_vals = [np.nan_to_num(result['ga_diffs'][g]) for g in groups]
            vmax_within = max((np.abs(v).max() for v in ga_vals), default=1.0)
            if vmax_within == 0:
                vmax_within = 1.0

            # Within-group rows
            for row, grp in enumerate(groups):
                ax = fig.add_subplot(gs[row, col])
                data_plot = np.nan_to_num(result['ga_diffs'][grp])
                mask = result['within_group_masks'].get(grp)
                if mask is not None and not np.any(mask):
                    mask = None

                plot_topomap(
                    data_plot, info, axes=ax,
                    cmap=PUBLICATION_PARAMS['colors']['cmap'],
                    vlim=(-vmax_within, vmax_within),
                    show=False, contours=4, sensors=True,
                    mask=mask,
                    mask_params=sm_params if mask is not None else None,
                )
                if col == 0:
                    n = result['n_subjects'][grp]
                    ax.set_ylabel(f"{grp} (n={n})\n(within-group)",
                                  fontsize=9, fontweight='bold')
                if row == 0:
                    ax.set_title(f"{band_name}\n{band_range[0]}-{band_range[1]} Hz",
                                 fontsize=9)

            # Between-group rows
            for row_off, (grp_a, grp_b) in enumerate(group_pairs):
                row = len(groups) + row_off
                pair_key = f"{grp_a} vs {grp_b}"
                pair_data = result['between_group'][pair_key]
                stat = pair_data['statistics']
                p_best = self._best_p(stat)
                stars = self._stars(p_best)

                ax = fig.add_subplot(gs[row, col])
                data_plot = np.nan_to_num(pair_data['ga_diff'])
                vmax_pair = np.abs(data_plot).max() or 1.0

                mask = pair_data.get('sig_mask_plot')
                if mask is not None and not np.any(mask):
                    mask = None

                plot_topomap(
                    data_plot, info, axes=ax,
                    cmap=PUBLICATION_PARAMS['colors']['cmap'],
                    vlim=(-vmax_pair, vmax_pair),
                    show=False, contours=4, sensors=True,
                    mask=mask,
                    mask_params=sm_params if mask is not None else None,
                )
                if col == 0:
                    label = f"{grp_a} vs {grp_b}"
                    if stars:
                        label += f" {stars}"
                    ax.set_ylabel(label, fontsize=9, fontweight='bold',
                                  color='darkred' if stars else 'black')

        filename = (f"{comparison_name}_summary.png"
                    if comparison_name else "summary_all_bands.png")
        output_file = self.figures_dir / filename
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                    bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()
        return str(output_file)

    # ------------------------------------------------------------------
    # Statistics table
    # ------------------------------------------------------------------

    def plot_statistics_table(self, all_results: Dict,
                               comparison_name: str = None,
                               sig_alpha: float = 0.05):
        """Generate within-group table + one between-group table per pair. Returns list of paths."""
        paths = []
        p = self._plot_within_table(all_results, comparison_name, sig_alpha)
        if p:
            paths.append(p)
        for p in self._plot_between_tables(all_results, comparison_name, sig_alpha):
            paths.append(p)
        return paths

    # ------ per-table helpers ------

    @staticmethod
    def _pstr(p: float) -> str:
        return f"{p:.4f}" if p < 1.0 else "n.s."

    @staticmethod
    def _tstr(v: float) -> str:
        return f"{v:.3f}"

    @staticmethod
    def _method_label(method: str) -> str:
        return {
            'ttest_fdr':                        'Independent t-test + FDR',
            'paired_ttest_fdr':                 'Paired t-test + FDR',
            'within_group_ttest_fdr':           'Paired t-test + FDR',
            'within_group_cluster_permutation': 'Cluster-based Permutation',
            'cluster_permutation':              'Cluster-based Permutation',
        }.get(method, method)

    def _render_table(self, table_data, columns, col_widths,
                      title: str, header_color: str,
                      sig_col_indices, sig_alpha: float,
                      filename: str):
        """Shared rendering + save logic for both tables."""
        import csv
        n_cols = len(columns)
        fig_w = max(14, 1.5 * n_cols)
        fig_h = 3.2 + 0.55 * len(table_data)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor='white')
        ax.axis('off')
        fig.suptitle(title, fontsize=12, fontweight='bold', y=0.98)

        table = ax.table(cellText=table_data, colLabels=columns,
                         loc='center', cellLoc='center', colWidths=col_widths)
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 2.0)

        for j in range(n_cols):
            cell = table[(0, j)]
            cell.set_facecolor(header_color)
            cell.set_text_props(color='white', fontweight='bold')

        for i, row_data in enumerate(table_data):
            row_idx = i + 1
            sig_found = any(row_data[j] in ('*', '**', '***')
                            for j in sig_col_indices if j < len(row_data))
            trend_found = any(row_data[j] == '^'
                              for j in sig_col_indices if j < len(row_data))
            bg = ('#c8e6c9' if sig_found else
                  '#fff9c4' if trend_found else
                  '#f5f5f5' if i % 2 == 0 else 'white')
            for j in range(n_cols):
                cell = table[(row_idx, j)]
                cell.set_facecolor(bg)
                if j in sig_col_indices and row_data[j]:
                    cell.set_text_props(fontweight='bold')

        fig.text(0.01, 0.01,
                 f"*** p<0.001  ** p<0.01  * p<0.05  ^ p<{sig_alpha*2:.2f} (trend)"
                 "  |  p(+) = positive cluster  p(-) = negative cluster"
                 "  |  Sig Ch = significant channels",
                 fontsize=7.5, color='#555555')

        output_file = self.figures_dir / filename
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                    bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        try:
            csv_file = self.output_dir / filename.replace('.png', '.csv')
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([c.replace('\n', ' ') for c in columns])
                writer.writerows(table_data)
        except Exception:
            pass

        return str(output_file)

    def _plot_within_table(self, all_results: Dict,
                            comparison_name: str = None,
                            sig_alpha: float = 0.05) -> Optional[str]:
        """Within-group stats table: Band x Group with full t-stats and cluster p-values."""
        band_names = list(all_results.keys())
        if not band_names:
            return None

        first = all_results[band_names[0]]
        groups = first['groups']

        table_data = []
        for band_name in band_names:
            result = all_results[band_name]
            row = [band_name, f"{result['band_range'][0]}-{result['band_range'][1]}"]
            for grp in groups:
                stat = result['within_group'].get(grp, {})
                t_obs = stat.get('t_obs', np.zeros(1))
                t_mean = float(np.mean(t_obs))
                t_min  = float(np.min(t_obs))
                t_max  = float(np.max(t_obs))
                p_pos = stat['positive_clusters'][0]['pval'] \
                    if stat.get('positive_clusters') else 1.0
                p_neg = stat['negative_clusters'][0]['pval'] \
                    if stat.get('negative_clusters') else 1.0
                n_sig = int(np.sum(stat.get('sig_mask', [])))
                best_p = min(p_pos, p_neg)
                row.extend([self._tstr(t_mean), self._tstr(t_min), self._tstr(t_max),
                             self._pstr(p_pos), self._pstr(p_neg),
                             str(n_sig), self._stars(best_p, alpha=sig_alpha)])
            table_data.append(row)

        # 7 stat columns per group
        per_grp = ['t(mean)', 't(min)', 't(max)', 'p(+)', 'p(-)', 'Sig Ch', 'Sig']
        grp_headers = []
        for grp in groups:
            n = first['n_subjects'][grp]
            grp_headers.extend([f"{grp} (n={n})\n{c}" for c in per_grp])
        columns = ['Band', 'Hz'] + grp_headers

        # Sig column indices: every 7th starting at offset 2+6
        sig_col_idx = [2 + 7 * k + 6 for k in range(len(groups))]

        col_widths = ([0.07, 0.06] +
                      [0.07, 0.07, 0.07, 0.08, 0.08, 0.06, 0.04] * len(groups))

        # Method from first group's first band
        method = first['within_group'].get(groups[0], {}).get('method', '')
        session_1, session_2 = first['session_1'], first['session_2']
        title = (f"Within-Group Results: {comparison_name}\n"
                 if comparison_name else "Within-Group Statistical Results\n")
        title += f"{session_2} vs {session_1}  |  Method: {self._method_label(method)}"

        filename = (f"{comparison_name}_within_table.png"
                    if comparison_name else "within_table.png")

        return self._render_table(
            table_data, columns, col_widths, title,
            header_color='#1565C0',
            sig_col_indices=sig_col_idx,
            sig_alpha=sig_alpha,
            filename=filename,
        )

    def _plot_between_tables(self, all_results: Dict,
                              comparison_name: str = None,
                              sig_alpha: float = 0.05) -> List[str]:
        """One between-group stats table per group pair. Returns list of paths."""
        band_names = list(all_results.keys())
        if not band_names:
            return []

        first = all_results[band_names[0]]
        groups = first['groups']
        group_pairs = list(combinations(groups, 2))
        if not group_pairs:
            return []

        columns = ['Band', 'Hz', 't(mean)', 't(min)', 't(max)',
                   'p(+)', 'p(-)', 'Sig Ch', 'Sig']
        col_widths = [0.09, 0.07, 0.09, 0.09, 0.09, 0.09, 0.09, 0.07, 0.05]
        sig_col_idx = [8]  # 'Sig' is always the last column

        session_1, session_2 = first['session_1'], first['session_2']
        paths = []

        for grp_a, grp_b in group_pairs:
            pk = f"{grp_a} vs {grp_b}"

            # Build one row per band for this pair
            table_data = []
            method = ''
            for band_name in band_names:
                result = all_results[band_name]
                pair_data = result['between_group'].get(pk, {})
                stat = pair_data.get('statistics', {})
                if not method:
                    method = stat.get('method', '')
                t_obs = stat.get('t_obs', np.zeros(1))
                t_mean = float(np.mean(t_obs))
                t_min  = float(np.min(t_obs))
                t_max  = float(np.max(t_obs))
                p_pos = stat['positive_clusters'][0]['pval'] \
                    if stat.get('positive_clusters') else 1.0
                p_neg = stat['negative_clusters'][0]['pval'] \
                    if stat.get('negative_clusters') else 1.0
                n_sig = int(np.sum(stat.get('sig_mask', [])))
                best_p = min(p_pos, p_neg)
                table_data.append([
                    band_name,
                    f"{result['band_range'][0]}-{result['band_range'][1]}",
                    self._tstr(t_mean), self._tstr(t_min), self._tstr(t_max),
                    self._pstr(p_pos), self._pstr(p_neg),
                    str(n_sig), self._stars(best_p, alpha=sig_alpha),
                ])

            na = first['n_subjects'][grp_a]
            nb = first['n_subjects'][grp_b]
            title = (f"Between-Group Results: {comparison_name}\n"
                     if comparison_name else "Between-Group Statistical Results\n")
            title += (f"{grp_a} (n={na}) vs {grp_b} (n={nb})  |  "
                      f"{session_2} vs {session_1}  |  Method: {self._method_label(method)}")

            # Sanitize pair key for filename
            pair_slug = pk.replace(' ', '_').replace('/', '_')
            prefix = f"{comparison_name}_" if comparison_name else ""
            filename = f"{prefix}between_{pair_slug}_table.png"

            p = self._render_table(
                table_data, columns, col_widths, title,
                header_color='#2E7D32',
                sig_col_indices=sig_col_idx,
                sig_alpha=sig_alpha,
                filename=filename,
            )
            if p:
                paths.append(p)

        return paths

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _best_p(stat: Dict) -> float:
        p_pos = stat['positive_clusters'][0]['pval'] \
            if stat.get('positive_clusters') else 1.0
        p_neg = stat['negative_clusters'][0]['pval'] \
            if stat.get('negative_clusters') else 1.0
        return min(p_pos, p_neg)

    @staticmethod
    def _stars(p: float, alpha: float = 0.05) -> str:
        if p < 0.001:
            return '***'
        if p < 0.01:
            return '**'
        if p < alpha:
            return '*'
        if p < alpha * 2:
            return '^'
        return ''


# ---------------------------------------------------------------------------
# Run function (test / CLI)
# ---------------------------------------------------------------------------

def run_analysis(
    data_path: str,
    output_path: str,
    fast: bool = False,
    n_permutations: int = None,
    max_epochs: int = None,
    resample_rate: int = None,
) -> Dict:
    """
    Run the universal analysis on any root directory with N groups.

    Args:
        data_path     : Root folder containing Group X / Session Y / SubNN.set structure
        output_path   : Where to save figures and tables
        fast          : Quick-test mode (50 permutations, 30 epochs per subject)
        n_permutations: Override permutation count (default: DEFAULT_PARAMS value = 5000)
        max_epochs    : Override max epochs per subject (default: 120)
        resample_rate : Override resampling rate (default: None = keep original)

    Returns:
        Nested dict: results[comparison_name][band_name] = band_result_dict
    """
    from py_config import DEFAULT_PARAMS

    config = {
        'root_dir': data_path,
        'output_dir': output_path,
        **DEFAULT_PARAMS,
    }

    if fast:
        config['n_permutations'] = 50
        config['max_epochs'] = 30
        config['n_jobs'] = 1

    if n_permutations is not None:
        config['n_permutations'] = n_permutations
    if max_epochs is not None:
        config['max_epochs'] = max_epochs
    if resample_rate is not None:
        config['resample_rate'] = resample_rate

    os.makedirs(output_path, exist_ok=True)

    # -- Analysis --
    print(f"\nData   : {data_path}")
    print(f"Output : {output_path}")
    print(f"n_permutations = {config['n_permutations']}, "
          f"max_epochs = {config['max_epochs']}\n")

    analyzer = UniversalFrequencyAnalyzer(config)
    results = analyzer.run_analysis()

    # -- Visualisation --
    viz = UniversalResultVisualizer(Path(output_path))

    for comparison_name, pair_results in results.items():
        if not pair_results:
            print(f"\n[SKIP] {comparison_name}: no band results")
            continue

        print(f"\n--- Saving figures: {comparison_name} ---")

        # Individual band figures
        for band_name, band_result in pair_results.items():
            try:
                path = viz.plot_band_result(
                    band_result, comparison_name=comparison_name)
                print(f"  Band  : {path}")
            except Exception as e:
                print(f"  [WARN] {band_name} band figure failed: {e}")

        # Summary figure
        try:
            path = viz.plot_summary(
                pair_results, comparison_name=comparison_name)
            print(f"  Summary: {path}")
        except Exception as e:
            print(f"  [WARN] Summary failed: {e}")

        # Statistics tables (within-group + between-group)
        try:
            sig_alpha = config.get('significance_alpha', 0.05)
            paths = viz.plot_statistics_table(
                pair_results,
                comparison_name=comparison_name,
                sig_alpha=sig_alpha,
            )
            for p in paths:
                print(f"  Table  : {p}")
        except Exception as e:
            print(f"  [WARN] Stats table failed: {e}")

    print("\n=== Done ===")
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    DEFAULT_DATA = r"E:\ANN_DATA\Ann Preprocessed GEDAI\EC"
    DEFAULT_OUT  = r"E:\ANN_DATA\Ann Preprocessed GEDAI\EC\RESULTS_UNIVERSAL"

    parser = argparse.ArgumentParser(
        description='Universal EEG Frequency Analysis (N groups, all session pairs)')
    parser.add_argument('--data',   default=DEFAULT_DATA,
                        help='Root directory with Group/Session/.set structure')
    parser.add_argument('--output', default=DEFAULT_OUT,
                        help='Output directory for figures and tables')
    parser.add_argument('--fast',   action='store_true',
                        help='Quick-test: 50 permutations, 30 epochs (for validation)')
    parser.add_argument('--n_perm', type=int, default=None,
                        help='Number of permutations (overrides default 5000)')
    parser.add_argument('--max_epochs', type=int, default=None,
                        help='Max epochs per subject (overrides default 120)')
    parser.add_argument('--resample', type=int, default=None,
                        help='Resample to this Hz (default: keep original)')

    args = parser.parse_args()

    run_analysis(
        data_path=args.data,
        output_path=args.output,
        fast=args.fast,
        n_permutations=args.n_perm,
        max_epochs=args.max_epochs,
        resample_rate=args.resample,
    )
