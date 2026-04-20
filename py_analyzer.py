"""
Core analysis engine for EEG frequency analysis with cluster-based permutation testing
"""

import numpy as np
import mne
from mne.time_frequency import psd_array_welch
from mne.stats import permutation_cluster_test, permutation_cluster_1samp_test
from scipy import stats
from scipy.stats import ttest_ind, ttest_rel, false_discovery_control
from itertools import product
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
import warnings

from py_config import FREQUENCY_BANDS, DEFAULT_PARAMS
from py_data_loader import EEGDataLoader


class FrequencyAnalyzer:
    """Main analysis engine using MNE-Python"""

    def __init__(self, config: Dict, progress_callback: Optional[Callable] = None):
        self.config = config
        self.progress = progress_callback or (lambda msg: print(msg.encode('ascii', 'replace').decode()))
        self.loader = EEGDataLoader(config['root_dir'])

        # Store results
        self.results = {}
        self.grand_averages = {}
        self.detected_sfreq = None
        self.common_channels = None
        self.common_info = None
        
    def run_analysis(self):
        """Run complete analysis pipeline"""
        
        self.progress("=== Starting EEG Frequency Analysis ===")
        
        # Step 1: Load data
        self.progress("Step 1: Loading and processing data...")
        group_data = self._load_all_data()
        
        if not group_data:
            raise ValueError("Failed to load data")
        
        # Step 2: Get baseline/comparison sessions from config or auto-detect
        baseline_sessions = self.config.get('baseline_sessions', [])
        comparison_sessions = self.config.get('comparison_sessions', [])

        # Fallback: auto-detect from session names for backward compatibility
        if not baseline_sessions or not comparison_sessions:
            all_sessions = self.config.get('sessions', [])
            baseline_sessions = sorted([s for s in all_sessions if 'pre' in s.lower()])
            comparison_sessions = sorted([s for s in all_sessions if 'post' in s.lower()])

        if not baseline_sessions or not comparison_sessions:
            raise ValueError(
                "Need both baseline and comparison sessions.\n"
                "Either use folder names containing 'pre'/'post', "
                "or select session roles in the GUI."
            )

        # Build session pairs: each comparison paired with each baseline
        # 1 baseline + N comparisons -> N pairs (most common case)
        # M baselines + N comparisons -> M*N pairs (cartesian product)
        session_pairs = list(product(baseline_sessions, comparison_sessions))
        self.progress(f"Baseline sessions: {baseline_sessions}")
        self.progress(f"Comparison sessions: {comparison_sessions}")
        self.progress(f"Session pairs to analyze: {len(session_pairs)}")
        
        # Step 3: Process each session pair
        all_results = {}
        
        for baseline_session, comparison_session in session_pairs:
            pre_session = baseline_session
            post_session = comparison_session
            comparison_name = f"{post_session}_vs_{pre_session}"
            self.progress(f"\n{'='*60}")
            self.progress(f"Comparing: {post_session} vs {pre_session}")
            self.progress(f"{'='*60}")

            # --- Align channels once for this comparison pair ---
            groups = list(group_data.keys())
            group_a, group_b = groups[0], groups[1]

            pre_data_a, post_data_a = self._get_matched_session_data(
                group_data[group_a], pre_session, post_session)
            pre_data_b, post_data_b = self._get_matched_session_data(
                group_data[group_b], pre_session, post_session)

            if not pre_data_a or not post_data_a or not pre_data_b or not post_data_b:
                self.progress(f"  WARNING: Missing matched data, skipping this pair")
                all_results[comparison_name] = {}
                continue

            all_pair_data = pre_data_a + post_data_a + pre_data_b + post_data_b
            common_channels, common_info, excluded, plot_channels, plot_info = \
                self._align_channels_for_comparison(all_pair_data, comparison_name)

            if common_channels is None or plot_channels is None:
                self.progress(f"  WARNING: Not enough common channels, skipping")
                all_results[comparison_name] = {}
                continue

            # Remove excluded subjects
            if excluded:
                pre_data_a = [d for d in pre_data_a if d['subject_id'] not in excluded]
                post_data_a = [d for d in post_data_a if d['subject_id'] not in excluded]
                pre_data_b = [d for d in pre_data_b if d['subject_id'] not in excluded]
                post_data_b = [d for d in post_data_b if d['subject_id'] not in excluded]

            # --- Process each frequency band with the aligned data ---
            self.progress("Analyzing frequency bands...")
            pair_results = {}

            for band_name, band_range in FREQUENCY_BANDS.items():
                self.progress(f"  Processing {band_name} band ({band_range[0]}-{band_range[1]} Hz)...")

                try:
                    result = self._analyze_band_aligned(
                        pre_data_a, post_data_a,
                        pre_data_b, post_data_b,
                        group_a, group_b,
                        band_name, band_range,
                        common_channels, common_info,
                        plot_channels, plot_info,
                        pre_session, post_session
                    )

                    if result:
                        pair_results[band_name] = result
                        self.progress(f"    [OK] {band_name} complete")
                        self._print_statistics(result, band_name)

                except Exception as e:
                    self.progress(f"    [FAIL] {band_name} failed: {str(e)}")

            # Store results for this pair
            all_results[comparison_name] = pair_results
        
        self.progress("\n=== Analysis Complete ===")
        
        # If only one pair, return it directly for backward compatibility
        if len(all_results) == 1:
            self.results = list(all_results.values())[0]
        else:
            self.results = all_results
        
        return self.results
    
    def _load_all_data(self) -> Dict:
        """Load and preprocess all subjects for ALL sessions"""

        # Scan directory — exclude the output folder so it isn't treated as a group
        output_dir_name = Path(self.config.get("output_dir", "")).name
        exclude = [output_dir_name] if output_dir_name else []
        scan_info = self.loader.scan_directory(exclude_dirs=exclude)
        self.progress(f"  Found {scan_info['total_files']} .set files")
        self.progress(f"  Groups: {', '.join(scan_info['groups'])}")
        self.progress(f"  Sessions: {', '.join(scan_info['sessions'])}")

        # Get baseline/comparison sessions from config or auto-detect
        baseline_sessions = self.config.get('baseline_sessions', [])
        comparison_sessions = self.config.get('comparison_sessions', [])

        # Fallback: auto-detect from session names
        if not baseline_sessions or not comparison_sessions:
            baseline_sessions = sorted([s for s in scan_info['sessions'] if 'pre' in s.lower()])
            comparison_sessions = sorted([s for s in scan_info['sessions'] if 'post' in s.lower()])

        if not baseline_sessions or not comparison_sessions:
            raise ValueError(
                "Need both baseline and comparison sessions.\n"
                "Either use folder names containing 'pre'/'post', "
                "or select session roles in the GUI."
            )

        self.progress(f"  Baseline sessions to load: {baseline_sessions}")
        self.progress(f"  Comparison sessions to load: {comparison_sessions}")

        # Load data for each group, organized by session
        # Structure: group_data[group][session] = {'subjects': [...], 'data': [...]}
        group_data = {}
        resample_rate = self.config.get('resample_rate', None)

        for group in scan_info['groups']:
            group_data[group] = {}

            # Load ALL sessions (baseline + comparison) for this group
            all_sessions = sorted(set(baseline_sessions + comparison_sessions))

            for session in all_sessions:
                # Get subjects for this session
                session_path = self.loader.root_dir / group / session
                if not session_path.exists():
                    self.progress(f"  WARNING: {group}/{session} does not exist")
                    continue

                set_files = list(session_path.glob('*.set'))
                subjects = [f.stem for f in set_files]

                if not subjects:
                    self.progress(f"  WARNING: No subjects found in {group}/{session}")
                    continue

                self.progress(f"  Loading {group}/{session}: {len(subjects)} subjects...")

                group_data[group][session] = {
                    'subjects': subjects,
                    'data': []
                }

                # Load each subject for this session
                ignore_epochs = self.config.get('ignore_epochs', True)
                max_epochs = self.config.get('max_epochs', None) or None
                apply_epoch_rejection = self.config.get('apply_epoch_rejection', True)
                for subj in subjects:
                    try:
                        filepath = session_path / f"{subj}.set"
                        raw = self.loader.load_set_file(
                            filepath,
                            resample_rate,
                            ignore_epochs=ignore_epochs,
                            max_epochs=max_epochs,
                            apply_epoch_rejection=apply_epoch_rejection
                        )

                        # Detect sampling rate from first successfully loaded file
                        if self.detected_sfreq is None:
                            self.detected_sfreq = raw.info['sfreq']
                            self.progress(f"  Detected sampling rate: {self.detected_sfreq} Hz")

                        # Process
                        psd = self._compute_psd(raw)

                        if psd is not None:
                            # Store with subject ID for matching
                            psd['subject_id'] = subj
                            group_data[group][session]['data'].append(psd)

                    except Exception as e:
                        self.progress(f"    Warning: Failed to load {subj}: {str(e)}")

                n_loaded = len(group_data[group][session]['data'])
                self.progress(f"    Successfully loaded: {n_loaded}/{len(subjects)}")

        return group_data

    def _align_channels_for_comparison(
        self,
        psd_list: List[Dict],
        label: str = "",
    ) -> Tuple[Optional[List[str]], Optional[object], set, Optional[List[str]], Optional[object]]:
        """Find common and union channels for one comparison.

        Progressively excludes subjects with the fewest channels (up to 25%)
        when the strict intersection is below MIN_COMMON_CHANNELS.

        Args:
            psd_list: Flat list of PSD dicts (pre+post for both groups).
            label:    Human-readable label for log messages.

        Returns:
            (common_channels, common_info, excluded_subject_ids,
             plot_channels, plot_info)
        """

        MIN_COMMON_CHANNELS = 5

        if not psd_list:
            return None, None, set(), None, None

        # Collect per-subject channel sets (a subject appears with pre AND post)
        from collections import defaultdict
        subj_ch_sets = defaultdict(list)   # subject_id -> [ch_set, ...]
        ref_info = None
        info_candidates = []

        for psd_dict in psd_list:
            ch_set = set(psd_dict['ch_names'])
            subj_ch_sets[psd_dict['subject_id']].append(ch_set)
            info_candidates.append((psd_dict['info'], ch_set))

        # Per-subject "usable" channels = intersection of their own sessions
        subj_common = {}
        for sid, sets in subj_ch_sets.items():
            subj_common[sid] = set.intersection(*sets)

        total_unique = sorted(set.union(*subj_common.values()))
        all_sets = list(subj_common.values())
        common = sorted(set.intersection(*all_sets))
        excluded = set()

        # Progressive exclusion if too few channels
        if len(common) < MIN_COMMON_CHANNELS:
            self.progress(f"    Strict common channels ({label}): {len(common)} "
                          f"(below minimum {MIN_COMMON_CHANNELS})")

            worst = sorted(subj_common.items(), key=lambda x: len(x[1]))
            max_exclude = max(1, len(subj_common) // 4)

            for sid, ch_set in worst:
                if len(common) >= MIN_COMMON_CHANNELS:
                    break
                if len(excluded) >= max_exclude:
                    break

                remaining = {k: v for k, v in subj_common.items()
                             if k not in excluded and k != sid}
                if not remaining:
                    break

                new_common = sorted(set.intersection(*remaining.values()))
                if len(new_common) > len(common):
                    common = new_common
                    excluded.add(sid)
                    self.progress(f"      Excluding {sid} ({len(ch_set)} ch) "
                                  f"-> {len(common)} common channels")

            if excluded:
                self.progress(f"    Excluded {len(excluded)} subject(s): "
                              f"{', '.join(sorted(excluded))}")

        self.progress(f"    Channels for {label}: {len(common)} common "
                      f"out of {len(total_unique)} unique")
        self.progress(f"    Using: {', '.join(common)}")

        if len(common) < 2:
            self.progress(f"    [WARNING] Only {len(common)} channel(s) in common - skipping")
            return None, None, excluded, None, None

        # Pick a reference Info that maximizes channel coverage for plotting
        total_unique_set = set(total_unique)
        if info_candidates:
            # Channel frequency across subjects (favor rare channels)
            ch_freq = {}
            for ch_set in subj_common.values():
                for ch in ch_set:
                    ch_freq[ch] = ch_freq.get(ch, 0) + 1

            def ref_score(candidate):
                info, ch_set = candidate
                overlap = ch_set & total_unique_set
                overlap_len = len(overlap)
                rarity_score = sum(1.0 / ch_freq.get(ch, 1) for ch in overlap)
                return (overlap_len, rarity_score, len(ch_set))

            ref_info = max(info_candidates, key=ref_score)[0]

        # Build reference Info with only common channels
        ref_ch_names = list(ref_info.ch_names)
        common_in_ref = [ch for ch in common if ch in ref_ch_names]
        if len(common_in_ref) != len(common):
            missing = sorted(set(common) - set(common_in_ref))
            self.progress(f"    [WARNING] {len(missing)} common channel(s) missing from ref info: "
                          f"{', '.join(missing)}")
        if len(common_in_ref) < 2:
            self.progress(f"    [WARNING] Only {len(common_in_ref)} usable common channel(s) "
                          f"after ref filtering - skipping")
            return None, None, excluded, None, None

        pick_idx = [ref_ch_names.index(ch) for ch in common_in_ref]
        common_info = mne.pick_info(ref_info.copy(), pick_idx)

        # Build plotting Info with union channels (shows all channels per comparison)
        plot_channels = [ch for ch in total_unique if ch in ref_ch_names]
        missing_plot = sorted(set(total_unique) - set(plot_channels))
        if missing_plot:
            self.progress(f"    [WARNING] {len(missing_plot)} channel(s) missing from ref info "
                          f"(will be skipped in plots): {', '.join(missing_plot)}")
        if not plot_channels:
            self.progress("    [WARNING] No plot channels available after ref filtering - skipping")
            return None, None, excluded, None, None

        plot_pick_idx = [ref_ch_names.index(ch) for ch in plot_channels]
        plot_info = mne.pick_info(ref_info.copy(), plot_pick_idx)

        return common_in_ref, common_info, excluded, plot_channels, plot_info
    
    def _compute_psd(self, data_obj) -> Optional[Dict]:
        """Compute power spectral density.

        Accepts either mne.io.Raw (continuous or concatenated) or mne.Epochs.
        For Epochs, PSD is computed per epoch and averaged.
        """

        try:
            sfreq = data_obj.info['sfreq']
            freq_range = self.config.get('freq_range', (1, 45))
            n_fft = int(self.config.get('epoch_length', 2.0) * sfreq)

            if isinstance(data_obj, mne.BaseEpochs):
                # Epoched data: compute PSD per epoch, then average
                data = data_obj.get_data()  # (n_epochs, n_channels, n_times)

                # Cap n_fft to the actual epoch length to avoid Welch errors
                n_times = data.shape[-1]
                n_fft = min(n_fft, n_times)

                # psd_array_welch handles 3D input: returns (n_epochs, n_channels, n_freqs)
                psds, freqs = psd_array_welch(
                    data,
                    sfreq=sfreq,
                    fmin=freq_range[0],
                    fmax=freq_range[1],
                    n_fft=n_fft,
                    n_overlap=n_fft // 2,
                    verbose=False
                )
                # Average PSDs across epochs -> (n_channels, n_freqs)
                psds = np.mean(psds, axis=0)
            else:
                # Continuous/Raw data
                data = data_obj.get_data()  # (n_channels, n_times)

                # Cap n_fft to the actual signal length to avoid Welch errors
                n_times = data.shape[-1]
                n_fft = min(n_fft, n_times)

                psds, freqs = psd_array_welch(
                    data,
                    sfreq=sfreq,
                    fmin=freq_range[0],
                    fmax=freq_range[1],
                    n_fft=n_fft,
                    n_overlap=n_fft // 2,
                    verbose=False
                )

            return {
                'psds': psds,
                'freqs': freqs,
                'ch_names': data_obj.ch_names,
                'info': data_obj.info
            }

        except Exception as e:
            self.progress(f"      PSD computation failed: {str(e)}")
            return None
    
    def _analyze_band_aligned(self, pre_data_a, post_data_a,
                              pre_data_b, post_data_b,
                              group_a, group_b,
                              band_name, band_range,
                              common_channels, common_info,
                              plot_channels, plot_info,
                              pre_session, post_session) -> Optional[Dict]:
        """Analyze one frequency band using pre-aligned, pre-filtered data.

        Channel alignment and subject exclusion are already done by the caller
        (run_analysis), so this method only computes band power differences
        and runs the statistical test.
        """

        # Extract band power and compute differences
        diff_a = self._compute_band_differences(
            pre_data_a, post_data_a, band_range, common_channels)
        diff_b = self._compute_band_differences(
            pre_data_b, post_data_b, band_range, common_channels)

        if diff_a is None or diff_b is None:
            return None

        # Check sample size
        n_a, n_b = len(diff_a), len(diff_b)
        self.progress(f"    Sample sizes: {group_a}={n_a}, {group_b}={n_b}")

        if n_a < 5 or n_b < 5:
            self.progress(f"    [WARNING] Sample size too small (min recommended: 5)")
            if n_b < 3:
                self.progress(f"    [WARNING] Group {group_b} (n={n_b}) is critically underpowered")

        # Compute grand averages for plotting (use union channels)
        plot_diff_a = self._compute_band_differences(
            pre_data_a, post_data_a, band_range, plot_channels, allow_missing=True)
        plot_diff_b = self._compute_band_differences(
            pre_data_b, post_data_b, band_range, plot_channels, allow_missing=True)

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            ga_diff_a = np.nanmean(plot_diff_a, axis=0)
            ga_diff_b = np.nanmean(plot_diff_b, axis=0)
        ga_a_vs_b = ga_diff_a - ga_diff_b

        # Diagnostic check
        diff_abs = np.abs(ga_diff_a - ga_diff_b)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            mean_diff = np.nanmean(diff_abs)
            max_diff = np.nanmax(diff_abs)

        if np.isnan(mean_diff) or np.isnan(max_diff):
            self.progress("    [WARNING] Group difference contains only NaNs (no overlapping channels)")
        elif mean_diff < 1e-10:
            self.progress(f"    [WARNING] Groups appear IDENTICAL (diff={mean_diff:.2e})")
        else:
            self.progress(f"    [OK] Group difference: mean={mean_diff:.2e}, max={max_diff:.2e}")

        # Run interaction test (Group A change vs Group B change)
        stat_result = self._run_cluster_test(diff_a, diff_b, info=common_info)

        # Run within-group tests (paired: pre vs post within each group)
        self.progress(f"    Running within-group test for {group_a}...")
        stat_group_a = self._run_within_group_test(diff_a, info=common_info)
        self.progress(f"    Running within-group test for {group_b}...")
        stat_group_b = self._run_within_group_test(diff_b, info=common_info)

        # Helper: map a sig_mask on common_channels -> plot_channels
        def _map_to_plot(sig_mask):
            out = np.zeros(len(plot_channels), dtype=bool)
            if sig_mask is not None and np.any(sig_mask):
                common_index = {ch: i for i, ch in enumerate(common_channels)}
                for i, ch in enumerate(plot_channels):
                    idx = common_index.get(ch)
                    if idx is not None and sig_mask[idx]:
                        out[i] = True
            return out

        sig_mask_plot = _map_to_plot(stat_result.get('sig_mask'))
        sig_mask_group_a_plot = _map_to_plot(stat_group_a.get('sig_mask'))
        sig_mask_group_b_plot = _map_to_plot(stat_group_b.get('sig_mask'))

        return {
            'band_name': band_name,
            'band_range': band_range,
            'group_a': group_a,
            'group_b': group_b,
            'n_subj_a': len(diff_a),
            'n_subj_b': len(diff_b),
            'ga_diff_a': ga_diff_a,
            'ga_diff_b': ga_diff_b,
            'ga_a_vs_b': ga_a_vs_b,
            'statistics': stat_result,           # interaction: group A vs group B
            'statistics_group_a': stat_group_a,  # within-group: group A pre->post
            'statistics_group_b': stat_group_b,  # within-group: group B pre->post
            'ch_names': plot_channels,
            'info': plot_info,
            'sig_mask_plot': sig_mask_plot,
            'sig_mask_group_a_plot': sig_mask_group_a_plot,
            'sig_mask_group_b_plot': sig_mask_group_b_plot,
            'common_ch_names': common_channels,
            'pre_session': pre_session,
            'post_session': post_session
        }
    
    def _get_matched_session_data(self, group_sessions: Dict, pre_session: str,
                                    post_session: str) -> Tuple[List, List]:
        """Get matched subject data for a specific Pre/Post session pair.

        Args:
            group_sessions: Dict with session names as keys, each containing 'subjects' and 'data'
            pre_session: Name of Pre session (e.g., 'Pre1', 'Pre2')
            post_session: Name of Post session (e.g., 'Post1', 'Post2')

        Returns:
            Tuple of (pre_data_list, post_data_list) for matched subjects
        """
        if pre_session not in group_sessions or post_session not in group_sessions:
            return [], []

        pre_session_data = group_sessions[pre_session]
        post_session_data = group_sessions[post_session]

        # Build lookup by subject ID
        pre_by_subject = {d['subject_id']: d for d in pre_session_data['data']}
        post_by_subject = {d['subject_id']: d for d in post_session_data['data']}

        # Find matched subjects (present in both sessions)
        matched_subjects = sorted(set(pre_by_subject.keys()) & set(post_by_subject.keys()))

        if not matched_subjects:
            return [], []

        # Extract matched data in same order
        pre_data = [pre_by_subject[subj] for subj in matched_subjects]
        post_data = [post_by_subject[subj] for subj in matched_subjects]

        return pre_data, post_data

    def _compute_band_differences(self, pre_data: List, post_data: List,
                                  band_range: Tuple,
                                  common_channels: List[str],
                                  allow_missing: bool = False) -> Optional[np.ndarray]:
        """Compute Post-Pre difference for a frequency band.

        Subsets each subject's PSD to *common_channels* before computing
        the difference, so subjects with different channel sets still work.
        """

        if not pre_data or not post_data or len(pre_data) != len(post_data):
            return None

        differences = []

        for pre, post in zip(pre_data, post_data):
            # Subset to common channels
            pre_ch = list(pre['ch_names'])
            post_ch = list(post['ch_names'])

            # Get frequency indices for band
            freq_mask = (pre['freqs'] >= band_range[0]) & (pre['freqs'] <= band_range[1])

            if not allow_missing:
                pre_idx = [pre_ch.index(ch) for ch in common_channels]
                post_idx = [post_ch.index(ch) for ch in common_channels]

                # Average power in band (subset to common channels)
                band_power_pre = np.mean(pre['psds'][pre_idx][:, freq_mask], axis=1)
                band_power_post = np.mean(post['psds'][post_idx][:, freq_mask], axis=1)

                # Compute difference
                diff = band_power_post - band_power_pre
                differences.append(diff)
            else:
                pre_map = {ch: i for i, ch in enumerate(pre_ch)}
                post_map = {ch: i for i, ch in enumerate(post_ch)}
                idx = [i for i, ch in enumerate(common_channels)
                       if ch in pre_map and ch in post_map]
                pre_idx = [pre_map[common_channels[i]] for i in idx]
                post_idx = [post_map[common_channels[i]] for i in idx]

                diff = np.full(len(common_channels), np.nan)

                if pre_idx and post_idx:
                    band_power_pre = np.mean(pre['psds'][pre_idx][:, freq_mask], axis=1)
                    band_power_post = np.mean(post['psds'][post_idx][:, freq_mask], axis=1)
                    diff_vals = band_power_post - band_power_pre
                    diff[idx] = diff_vals

                differences.append(diff)

        return np.array(differences)
    
    def _adjacency_from_3d_positions(self, info, dist_threshold: float = 0.05):
        """Build adjacency from 3D electrode positions using a distance threshold.

        dist_threshold: metres.  0.05 m (5 cm) gives ~4-6 nearest neighbours
        for a standard 64-channel 10-10 layout, matching topological adjacency.
        Returns a scipy csr_matrix of shape (n_ch, n_ch), or None.
        """
        from scipy.sparse import csr_matrix
        from scipy.spatial.distance import cdist

        pos = np.array([ch['loc'][:3] for ch in info['chs']])
        valid = np.any(pos != 0, axis=1)
        if not np.any(valid):
            return None

        dists = cdist(pos, pos)
        adj = (dists < dist_threshold) & (dists > 0)
        return csr_matrix(adj.astype(np.float64))

    def _get_channel_adjacency(self, info):
        """Build spatial adjacency matrix for cluster permutation.

        Uses 3D electrode positions (not 2D projection) to avoid MNE's
        Delaunay failure on midline channels (AFZ, CZ, FCZ, etc.).

        config['adjacency_method']:
            'mne'  - apply standard_1020 montage then use 3D positions (default)
            'data' - use 3D positions already in the Info object (.set file)
            'none' - no adjacency (unconstrained, old behaviour)

        Returns a scipy sparse matrix or None.
        """
        method = self.config.get('adjacency_method', 'mne')
        if method == 'none':
            return None

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore')

            if method == 'data':
                try:
                    adj = self._adjacency_from_3d_positions(info)
                    if adj is not None:
                        self.progress(f"      Adjacency: data-based 3D positions ({info['nchan']} ch)")
                        return adj
                except Exception as e:
                    self.progress(f"      Data adjacency failed ({e}), falling back to MNE montage")

            # MNE standard_1020 — set montage then build from 3D positions
            try:
                info_copy = info.copy()
                montage = mne.channels.make_standard_montage('standard_1020')
                info_copy.set_montage(montage, on_missing='ignore', verbose=False)
                adj = self._adjacency_from_3d_positions(info_copy)
                if adj is not None:
                    self.progress(f"      Adjacency: MNE standard_1020 3D positions ({info['nchan']} ch)")
                    return adj
            except Exception as e:
                self.progress(f"      MNE adjacency failed ({e}), no spatial constraint used")

            return None

    def _run_cluster_test(self, data_a: np.ndarray, data_b: np.ndarray,
                          info=None) -> Dict:
        """Run statistical test based on user selection"""

        # Get parameters
        n_perm = self.config.get('n_permutations', 1000)
        cluster_alpha = self.config.get('cluster_alpha', 0.05)
        sig_alpha = self.config.get('significance_alpha', 0.05)
        tail = self.config.get('tail', 0)
        method = self.config.get('statistical_method', 'auto')

        n_a, n_b = len(data_a), len(data_b)
        MIN_SAMPLE_FOR_PERMUTATION = 5
        small_sample = (n_a < MIN_SAMPLE_FOR_PERMUTATION or n_b < MIN_SAMPLE_FOR_PERMUTATION)

        # Compute spatial adjacency for cluster methods
        adjacency = self._get_channel_adjacency(info) if info is not None else None

        # DECISION LOGIC
        if method == 'auto':
            # Automatic selection
            if small_sample:
                self.progress(f"      [WARNING] Small sample detected (n_a={n_a}, n_b={n_b})")
                self.progress(f"      -> Auto: Using independent t-tests with FDR correction")
                return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=False)
            else:
                self.progress(f"      -> Auto: Using cluster-based permutation test")
                return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha,
                                                     sig_alpha, tail, adjacency=adjacency)

        elif method == 'cluster':
            # Force cluster permutation
            if small_sample:
                self.progress(f"      [WARNING] Small sample (n_a={n_a}, n_b={n_b}) but forcing cluster test")
            self.progress(f"      -> Using cluster-based permutation test")
            return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha,
                                                 sig_alpha, tail, adjacency=adjacency)

        elif method == 'paired_ttest':
            # Paired t-test + FDR
            self.progress(f"      -> Using PAIRED t-tests with FDR correction")
            return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=True)

        elif method == 'independent_ttest':
            # Independent t-test + FDR
            self.progress(f"      -> Using INDEPENDENT t-tests with FDR correction")
            return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=False)

        else:
            # Fallback to cluster
            self.progress(f"      -> Unknown method, using cluster permutation")
            return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha,
                                                 sig_alpha, tail, adjacency=adjacency)
    
    def _run_cluster_permutation(self, data_a: np.ndarray, data_b: np.ndarray,
                                  n_perm: int, cluster_alpha: float,
                                  sig_alpha: float, tail: int,
                                  adjacency=None) -> Dict:
        """Cluster-based permutation test with optional spatial adjacency.

        adjacency: scipy sparse matrix (n_ch x n_ch) or None.
          When provided, only spatially contiguous channels form clusters,
          which tightens the null distribution and improves power.
        """

        threshold = stats.t.ppf(1 - cluster_alpha, data_a.shape[0] + data_b.shape[0] - 2)

        try:
            t_obs, clusters, cluster_pv, H0 = permutation_cluster_test(
                [data_a, data_b],
                n_permutations=n_perm,
                threshold=threshold,
                tail=tail,
                adjacency=adjacency,
                n_jobs=self.config.get('n_jobs', -1),
                verbose=False
            )

            # Parse clusters — MNE returns them as tuples of index arrays
            all_clusters = []
            if len(clusters) > 0 and len(cluster_pv) > 0:
                for cluster, pval in zip(clusters, cluster_pv):
                    # cluster is a tuple like (array([i, j, ...]),) for 1-D data
                    ch_idx = cluster[0] if isinstance(cluster, tuple) else np.where(cluster)[0]
                    if len(ch_idx) == 0:
                        continue
                    all_clusters.append({
                        'channels': ch_idx.tolist(),
                        'pval': float(pval),
                        't_values': t_obs[ch_idx].tolist()
                    })

            sig_clusters_pos = [c for c in all_clusters
                                 if np.mean(t_obs[c['channels']]) > 0]
            sig_clusters_neg = [c for c in all_clusters
                                 if np.mean(t_obs[c['channels']]) <= 0]
            sig_clusters_pos.sort(key=lambda x: x['pval'])
            sig_clusters_neg.sort(key=lambda x: x['pval'])

            # Significance mask (channels in clusters that pass sig_alpha)
            sig_mask = np.zeros(len(t_obs), dtype=bool)
            for c in sig_clusters_pos + sig_clusters_neg:
                if c['pval'] < sig_alpha:
                    sig_mask[c['channels']] = True

            return {
                't_obs': t_obs,
                'clusters': clusters,
                'cluster_pv': cluster_pv,
                'positive_clusters': sig_clusters_pos,
                'negative_clusters': sig_clusters_neg,
                'sig_mask': sig_mask,
                'H0': H0,
                'method': 'cluster_permutation'
            }

        except Exception as e:
            self.progress(f"      Statistics failed: {str(e)}")
            return {
                't_obs': np.zeros(data_a.shape[1]),
                'clusters': [],
                'cluster_pv': [],
                'positive_clusters': [],
                'negative_clusters': [],
                'sig_mask': np.zeros(data_a.shape[1], dtype=bool),
                'H0': None,
                'method': 'failed'
            }
    
    def _run_within_group_test(self, diff_data: np.ndarray, info=None) -> Dict:
        """One-sample cluster permutation test: H0 is that mean(diff) == 0.

        This is the within-group equivalent of MATLAB's depsamplesT — it tests
        whether the pre->post change within a single group is significant.

        diff_data: (n_subjects, n_channels) post-pre power differences.
        """
        n_perm = self.config.get('n_permutations', 5000)
        cluster_alpha = self.config.get('cluster_alpha', 0.05)
        sig_alpha = self.config.get('significance_alpha', 0.05)
        tail = self.config.get('tail', 0)

        n_subj, n_ch = diff_data.shape
        MIN_SAMPLE = self.config.get('min_sample_for_permutation', 5)

        adjacency = self._get_channel_adjacency(info) if info is not None else None

        # Threshold: one-sample t, df = n-1
        df = n_subj - 1
        threshold = stats.t.ppf(1 - cluster_alpha, df)

        if n_subj < MIN_SAMPLE:
            # Fall back to one-sample t-test + FDR per channel
            self.progress(f"      Within-group test: small sample (n={n_subj}), using 1-sample t + FDR")
            t_obs = np.zeros(n_ch)
            p_values = np.zeros(n_ch)
            for ch in range(n_ch):
                t_obs[ch], p_values[ch] = stats.ttest_1samp(diff_data[:, ch], 0)
            try:
                p_corrected = false_discovery_control(p_values, method='bh')
            except Exception:
                p_corrected = self._manual_fdr_correction(p_values)
            sig_mask = p_corrected < sig_alpha
            sig_clusters_pos = [{'channels': [ch], 'pval': float(p_corrected[ch]), 't_values': [float(t_obs[ch])]}
                                 for ch in range(n_ch) if sig_mask[ch] and t_obs[ch] > 0]
            sig_clusters_neg = [{'channels': [ch], 'pval': float(p_corrected[ch]), 't_values': [float(t_obs[ch])]}
                                 for ch in range(n_ch) if sig_mask[ch] and t_obs[ch] <= 0]
            return {
                't_obs': t_obs, 'clusters': [], 'cluster_pv': p_corrected,
                'positive_clusters': sorted(sig_clusters_pos, key=lambda x: x['pval']),
                'negative_clusters': sorted(sig_clusters_neg, key=lambda x: x['pval']),
                'sig_mask': sig_mask, 'H0': None, 'method': 'within_group_ttest_fdr'
            }

        try:
            t_obs, clusters, cluster_pv, H0 = permutation_cluster_1samp_test(
                diff_data,
                n_permutations=n_perm,
                threshold=threshold,
                tail=tail,
                adjacency=adjacency,
                n_jobs=self.config.get('n_jobs', -1),
                verbose=False
            )

            all_clusters = []
            for cluster, pval in zip(clusters, cluster_pv):
                ch_idx = cluster[0] if isinstance(cluster, tuple) else np.where(cluster)[0]
                if len(ch_idx) == 0:
                    continue
                all_clusters.append({
                    'channels': ch_idx.tolist(),
                    'pval': float(pval),
                    't_values': t_obs[ch_idx].tolist()
                })

            sig_clusters_pos = sorted(
                [c for c in all_clusters if np.mean(t_obs[c['channels']]) > 0],
                key=lambda x: x['pval'])
            sig_clusters_neg = sorted(
                [c for c in all_clusters if np.mean(t_obs[c['channels']]) <= 0],
                key=lambda x: x['pval'])

            sig_mask = np.zeros(len(t_obs), dtype=bool)
            for c in sig_clusters_pos + sig_clusters_neg:
                if c['pval'] < sig_alpha:
                    sig_mask[c['channels']] = True

            return {
                't_obs': t_obs, 'clusters': clusters, 'cluster_pv': cluster_pv,
                'positive_clusters': sig_clusters_pos,
                'negative_clusters': sig_clusters_neg,
                'sig_mask': sig_mask, 'H0': H0,
                'method': 'within_group_cluster_permutation'
            }

        except Exception as e:
            self.progress(f"      Within-group test failed: {str(e)}")
            return {
                't_obs': np.zeros(n_ch), 'clusters': [], 'cluster_pv': [],
                'positive_clusters': [], 'negative_clusters': [],
                'sig_mask': np.zeros(n_ch, dtype=bool), 'H0': None, 'method': 'failed'
            }

    def _run_ttest_fallback(self, data_a: np.ndarray, data_b: np.ndarray,
                            sig_alpha: float = 0.05, paired: bool = False) -> Dict:
        """Channel-wise t-tests with FDR correction (paired or independent)"""
        
        n_channels = data_a.shape[1]
        t_obs = np.zeros(n_channels)
        p_values = np.zeros(n_channels)
        
        # Check if paired test is possible
        if paired and len(data_a) != len(data_b):
            self.progress(f"      [WARNING] Cannot do paired test: n_a={len(data_a)} != n_b={len(data_b)}")
            self.progress(f"      -> Switching to independent t-test")
            paired = False
        
        # Run t-test for each channel
        for ch in range(n_channels):
            if paired:
                # Paired t-test (within-subject)
                t_obs[ch], p_values[ch] = ttest_rel(data_a[:, ch], data_b[:, ch])
            else:
                # Independent t-test (between-group)
                t_obs[ch], p_values[ch] = ttest_ind(data_a[:, ch], data_b[:, ch])
        
        # Apply FDR correction (Benjamini-Hochberg)
        skip_fdr = self.config.get('skip_fdr_correction', False)
        
        if skip_fdr:
            # Use raw p-values (no correction)
            p_corrected = p_values
            self.progress(f"      [WARNING] Using RAW p-values (FDR correction skipped)")
        else:
            # Apply FDR correction
            try:
                # scipy >= 1.10 has false_discovery_control
                p_corrected = false_discovery_control(p_values, method='bh')
            except (AttributeError, TypeError):
                # Fallback: manual FDR calculation
                p_corrected = self._manual_fdr_correction(p_values)
        
        # Create significance mask
        sig_mask = p_corrected < sig_alpha
        
        # Format as "clusters" for compatibility with visualization
        sig_clusters_pos = []
        sig_clusters_neg = []
        
        # Each significant channel is its own "cluster"
        for ch in range(n_channels):
            if sig_mask[ch]:
                cluster_info = {
                    'channels': [ch],
                    'pval': float(p_corrected[ch]),
                    't_values': [float(t_obs[ch])]
                }
                
                if t_obs[ch] > 0:
                    sig_clusters_pos.append(cluster_info)
                else:
                    sig_clusters_neg.append(cluster_info)
        
        # Sort by p-value
        sig_clusters_pos.sort(key=lambda x: x['pval'])
        sig_clusters_neg.sort(key=lambda x: x['pval'])
        
        # Report results
        test_type = "PAIRED" if paired else "INDEPENDENT"
        n_sig = np.sum(sig_mask)
        if n_sig > 0:
            self.progress(f"      [OK] Found {n_sig} significant channels ({test_type}, FDR-corrected)")
            min_p = np.min(p_corrected[sig_mask])
            self.progress(f"      [OK] Minimum p-value: {min_p:.4f}")
        else:
            self.progress(f"      -> No significant channels ({test_type}, FDR-corrected)")
        
        method_label = 'paired_ttest_fdr' if paired else 'ttest_fdr'
        
        return {
            't_obs': t_obs,
            'clusters': [],  # Not applicable for t-tests
            'cluster_pv': p_corrected,  # Store corrected p-values here
            'positive_clusters': sig_clusters_pos,
            'negative_clusters': sig_clusters_neg,
            'sig_mask': sig_mask,
            'H0': None,
            'method': method_label,
            'p_uncorrected': p_values,
            'p_corrected': p_corrected
        }
    
    def _manual_fdr_correction(self, p_values: np.ndarray) -> np.ndarray:
        """Manual FDR correction using Benjamini-Hochberg procedure"""
        
        n = len(p_values)
        sorted_idx = np.argsort(p_values)
        sorted_p = p_values[sorted_idx]
        
        # Benjamini-Hochberg critical values
        critical_values = (np.arange(1, n + 1) / n) * 0.05
        
        # Find largest i where p(i) <= (i/n)*alpha
        reject = sorted_p <= critical_values
        
        if np.any(reject):
            max_idx = np.where(reject)[0].max()
            threshold = sorted_p[max_idx]
            
            # Adjusted p-values
            p_adjusted = np.minimum(1, sorted_p * n / np.arange(1, n + 1))
            
            # Enforce monotonicity
            for i in range(n - 2, -1, -1):
                p_adjusted[i] = min(p_adjusted[i], p_adjusted[i + 1])
            
            # Unsort
            p_corrected = np.empty(n)
            p_corrected[sorted_idx] = p_adjusted
        else:
            p_corrected = np.ones(n)
        
        return p_corrected
    
    def _print_statistics(self, result: Dict, band_name: str):
        """Print statistical results for interaction and within-group tests."""

        def _report(label, st):
            pos = st.get('positive_clusters', [])
            neg = st.get('negative_clusters', [])
            if pos:
                self.progress(f"      [{label}] Positive clusters: best p={pos[0]['pval']:.4f}")
            if neg:
                self.progress(f"      [{label}] Negative clusters: best p={neg[0]['pval']:.4f}")
            if not pos and not neg:
                self.progress(f"      [{label}] No significant clusters")

        group_a = result.get('group_a', 'GroupA')
        group_b = result.get('group_b', 'GroupB')
        _report(f"Interaction ({group_a} vs {group_b})", result['statistics'])
        if 'statistics_group_a' in result:
            _report(f"Within {group_a} (pre->post)", result['statistics_group_a'])
        if 'statistics_group_b' in result:
            _report(f"Within {group_b} (pre->post)", result['statistics_group_b'])
