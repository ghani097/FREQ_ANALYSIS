"""
Publication-quality visualization for EEG frequency analysis results
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib import gridspec
from matplotlib.patches import Rectangle
import mne
from mne.viz import plot_topomap
from pathlib import Path
from typing import Dict, List, Optional

from py_config import PUBLICATION_PARAMS, FREQUENCY_BANDS


# Set publication defaults
mpl.rcParams['font.family'] = PUBLICATION_PARAMS['font']['family']
mpl.rcParams['font.size'] = PUBLICATION_PARAMS['font']['size']
mpl.rcParams['figure.dpi'] = PUBLICATION_PARAMS['figure']['dpi']
mpl.rcParams['savefig.dpi'] = PUBLICATION_PARAMS['figure']['dpi']
mpl.rcParams['savefig.facecolor'] = PUBLICATION_PARAMS['figure']['facecolor']


class ResultVisualizer:
    """Create publication-ready figures"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.figures_dir = self.output_dir / 'figures'
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        
    def plot_band_result(self, result: Dict, show: bool = False):
        """Create 3-panel topoplot for one frequency band"""
        
        band_name = result['band_name']
        band_range = result['band_range']
        comparison_name = result.get('comparison_name', '')
        
        # Use non-interactive backend to avoid threading issues
        import matplotlib
        matplotlib.use('Agg')  # Must be before importing pyplot
        
        # Create figure
        fig = plt.figure(figsize=(15, 5), facecolor='white')
        fig.suptitle(f'{band_name} Band ({band_range[0]}-{band_range[1]} Hz)',
                    fontsize=PUBLICATION_PARAMS['font']['title_size'],
                    fontweight='bold', y=0.98)
        
        # Get data
        ga_diff_a = result['ga_diff_a']
        ga_diff_b = result['ga_diff_b']
        ga_a_vs_b = result['ga_a_vs_b']
        info = result['info']
        stats = result['statistics']
        
        # Determine color limits
        vmax_diff = max(np.abs(ga_diff_a).max(), np.abs(ga_diff_b).max())
        if vmax_diff == 0:
            vmax_diff = 1
        
        vmax_comp = np.abs(ga_a_vs_b).max()
        if vmax_comp == 0:
            vmax_comp = 1
        
        # Panel 1: Group A
        ax1 = plt.subplot(1, 3, 1)
        im1, cn1 = plot_topomap(
            ga_diff_a,
            info,
            axes=ax1,
            cmap=PUBLICATION_PARAMS['colors']['cmap'],
            vlim=(-vmax_diff, vmax_diff),
            show=False,
            contours=PUBLICATION_PARAMS['topomap']['contours'],
            sensors=PUBLICATION_PARAMS['topomap']['sensors'],
            names=result['ch_names'] if PUBLICATION_PARAMS['topomap']['show_names'] else None
        )
        ax1.set_title(f"{result['group_a']}: {result['post_session']} - {result['pre_session']}\n"
                     f"(n={result['n_subj_a']})",
                     fontsize=PUBLICATION_PARAMS['font']['label_size'])
        
        # Panel 2: Group B
        ax2 = plt.subplot(1, 3, 2)
        im2, cn2 = plot_topomap(
            ga_diff_b,
            info,
            axes=ax2,
            cmap=PUBLICATION_PARAMS['colors']['cmap'],
            vlim=(-vmax_diff, vmax_diff),
            show=False,
            contours=PUBLICATION_PARAMS['topomap']['contours'],
            sensors=PUBLICATION_PARAMS['topomap']['sensors']
        )
        ax2.set_title(f"{result['group_b']}: {result['post_session']} - {result['pre_session']}\n"
                     f"(n={result['n_subj_b']})",
                     fontsize=PUBLICATION_PARAMS['font']['label_size'])
        
        # Panel 3: A vs B with significance
        ax3 = plt.subplot(1, 3, 3)
        
        # Determine significance level
        sig_level, sig_color, p_str = self._get_significance_info(stats)
        
        # Plot with highlighted channels
        mask = stats['sig_mask'] if np.any(stats['sig_mask']) else None
        
        im3, cn3 = plot_topomap(
            ga_a_vs_b,
            info,
            axes=ax3,
            cmap=PUBLICATION_PARAMS['colors']['cmap'],
            vlim=(-vmax_comp, vmax_comp),
            show=False,
            contours=PUBLICATION_PARAMS['topomap']['contours'],
            sensors=PUBLICATION_PARAMS['topomap']['sensors'],
            mask=mask,
            mask_params=dict(marker='X', markerfacecolor=PUBLICATION_PARAMS['colors']['sig_marker'], 
                           markersize=18, markeredgecolor='white',
                           markeredgewidth=2) if mask is not None else None
        )
        
        title_color = sig_color if sig_level != 'none' else 'black'
        title_weight = 'bold' if sig_level in ['strong', 'moderate', 'significant'] else 'normal'
        
        # Title without p-value, just group comparison
        ax3.set_title(f"{result['group_a']} vs {result['group_b']}",
                     fontsize=PUBLICATION_PARAMS['font']['label_size'],
                     color=title_color, fontweight=title_weight)
        
        # Add colorbars
        # Colorbar for panels 1-2
        cbar1_ax = fig.add_axes([0.37, 0.15, 0.015, 0.7])
        cbar1 = fig.colorbar(im2, cax=cbar1_ax)
        cbar1.set_label('Power Change (μV²/Hz)', 
                       fontsize=PUBLICATION_PARAMS['font']['label_size'])
        
        # Colorbar for panel 3
        cbar2_ax = fig.add_axes([0.92, 0.15, 0.015, 0.7])
        cbar2 = fig.colorbar(im3, cax=cbar2_ax)
        cbar2.set_label('Group Difference', 
                       fontsize=PUBLICATION_PARAMS['font']['label_size'])
        
        # Adjust layout
        plt.subplots_adjust(left=0.05, right=0.90, top=0.90, bottom=0.1, wspace=0.3)
        
        # Save
        filename_prefix = f'{comparison_name}_' if comparison_name else ''
        output_file = self.figures_dir / f'{filename_prefix}topo_{band_name}.png'
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                   bbox_inches='tight', facecolor='white', edgecolor='none')
        
        plt.close()  # Always close to free memory
        
        return str(output_file)
    
    def plot_summary(self, all_results: Dict, show: bool = False, comparison_name: str = None):
        """Create summary figure with all bands
        
        Args:
            all_results: Dictionary of band results
            show: Whether to display the figure
            comparison_name: Name of comparison (e.g., "Post1_vs_Pre1")
        """
        
        band_names = list(all_results.keys())
        n_bands = len(band_names)
        
        if n_bands == 0:
            return None
        
        # Use non-interactive backend
        import matplotlib
        matplotlib.use('Agg')
        
        # Create figure
        fig = plt.figure(figsize=(4*n_bands, 12), facecolor='white')
        
        # Add comparison name to title if provided
        if comparison_name:
            main_title = f'Frequency Analysis Summary: {comparison_name}'
        else:
            main_title = 'Frequency Analysis Summary: All Bands'
        
        fig.suptitle(main_title,
                    fontsize=PUBLICATION_PARAMS['font']['title_size'] + 2,
                    fontweight='bold', y=0.98)
        
        # Create grid
        gs = gridspec.GridSpec(3, n_bands, figure=fig, hspace=0.35, wspace=0.25,
                              left=0.05, right=0.95, top=0.92, bottom=0.08)
        
        for idx, band_name in enumerate(band_names):
            result = all_results[band_name]
            band_range = result['band_range']
            
            ga_diff_a = result['ga_diff_a']
            ga_diff_b = result['ga_diff_b']
            ga_a_vs_b = result['ga_a_vs_b']
            info = result['info']
            stats = result['statistics']
            
            # Determine color limits
            vmax = max(np.abs(ga_diff_a).max(), np.abs(ga_diff_b).max())
            if vmax == 0:
                vmax = 1
            
            # Row 1: Group A
            ax1 = fig.add_subplot(gs[0, idx])
            plot_topomap(
                ga_diff_a, info, axes=ax1,
                cmap=PUBLICATION_PARAMS['colors']['cmap'],
                vlim=(-vmax, vmax), show=False,
                contours=4, sensors=True
            )
            if idx == 0:
                ax1.set_ylabel(f"{result['group_a']}\n(Post-Pre)",
                              fontsize=PUBLICATION_PARAMS['font']['label_size'],
                              fontweight='bold')
            ax1.set_title(f"{band_name}\n{band_range[0]}-{band_range[1]} Hz",
                         fontsize=PUBLICATION_PARAMS['font']['size'] + 1)
            
            # Row 2: Group B
            ax2 = fig.add_subplot(gs[1, idx])
            plot_topomap(
                ga_diff_b, info, axes=ax2,
                cmap=PUBLICATION_PARAMS['colors']['cmap'],
                vlim=(-vmax, vmax), show=False,
                contours=4, sensors=True
            )
            if idx == 0:
                ax2.set_ylabel(f"{result['group_b']}\n(Post-Pre)",
                              fontsize=PUBLICATION_PARAMS['font']['label_size'],
                              fontweight='bold')
            
            # Row 3: A vs B
            ax3 = fig.add_subplot(gs[2, idx])
            vmax_comp = np.abs(ga_a_vs_b).max()
            if vmax_comp == 0:
                vmax_comp = 1
            
            mask = stats['sig_mask'] if np.any(stats['sig_mask']) else None
            sig_level, sig_color, p_str = self._get_significance_info(stats)
            
            plot_topomap(
                ga_a_vs_b, info, axes=ax3,
                cmap=PUBLICATION_PARAMS['colors']['cmap'],
                vlim=(-vmax_comp, vmax_comp), show=False,
                contours=4, sensors=True,
                mask=mask,
                mask_params=dict(marker='X', markerfacecolor=PUBLICATION_PARAMS['colors']['sig_marker'],
                               markersize=15, markeredgecolor='white',
                               markeredgewidth=1.5) if mask is not None else None
            )
            if idx == 0:
                ax3.set_ylabel(f"A vs B",
                              fontsize=PUBLICATION_PARAMS['font']['label_size'],
                              fontweight='bold')
            
            # No p-value label - just show significance via markers and color
        
        # Save with comparison name in filename
        if comparison_name:
            filename = f'{comparison_name}_summary.png'
        else:
            filename = 'summary_all_bands.png'
        
        output_file = self.figures_dir / filename
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                   bbox_inches='tight', facecolor='white', edgecolor='none')
        
        plt.close()  # Always close to free memory
        
        return str(output_file)
    
    def _get_significance_info(self, stats: Dict):
        """Determine significance level and formatting"""
        
        # Check if method is specified
        method = stats.get('method', 'cluster_permutation')
        
        p_values = []
        
        if stats['positive_clusters']:
            p_values.append(('pos', stats['positive_clusters'][0]['pval']))
        if stats['negative_clusters']:
            p_values.append(('neg', stats['negative_clusters'][0]['pval']))
        
        if not p_values:
            method_labels_short = {
                'ttest_fdr': ' (Ind-FDR)',
                'paired_ttest_fdr': ' (Paired-FDR)',
                'cluster_permutation': ''
            }
            method_str = method_labels_short.get(method, '')
            return 'none', 'black', f'No clusters{method_str}'
        
        # Get minimum p-value
        p_values.sort(key=lambda x: x[1])
        direction, min_p = p_values[0]
        
        # Determine significance level
        if min_p < 0.001:
            sig_level = 'strong'
            sig_color = PUBLICATION_PARAMS['colors']['strong']
            stars = '***'
        elif min_p < 0.01:
            sig_level = 'moderate'
            sig_color = PUBLICATION_PARAMS['colors']['moderate']
            stars = '**'
        elif min_p < 0.05:
            sig_level = 'significant'
            sig_color = PUBLICATION_PARAMS['colors']['significant']
            stars = '*'
        elif min_p < 0.10:
            sig_level = 'trend'
            sig_color = PUBLICATION_PARAMS['colors']['trend']
            stars = '†'
        else:
            sig_level = 'none'
            sig_color = 'black'
            stars = ''
        
        # Format p-value string with method indicator
        method_labels = {
            'ttest_fdr': 'Ind-FDR',
            'paired_ttest_fdr': 'Paired-FDR',
            'cluster_permutation': ''
        }
        method_suffix = method_labels.get(method, '')
        
        if min_p < 0.001:
            p_str = f"p{'+'if direction=='pos' else '-'}={min_p:.4f}{stars}"
        else:
            p_str = f"p{'+'if direction=='pos' else '-'}={min_p:.3f}{stars}"
        
        if method_suffix:
            p_str += f" ({method_suffix})"
        
        # Add second cluster if exists
        if len(p_values) > 1:
            direction2, p2 = p_values[1]
            if p2 < 0.10:
                stars2 = '***' if p2<0.001 else ('**' if p2<0.01 else ('*' if p2<0.05 else '†'))
                p_str += f", p{'+'if direction2=='pos' else '-'}={p2:.3f}{stars2}"
        
        return sig_level, sig_color, p_str

    def plot_statistics_table(self, all_results: Dict, comparison_name: str = None):
        """Create a table figure showing t-values and p-values for all bands.

        Args:
            all_results: Dictionary of band results
            comparison_name: Name of comparison (e.g., "Post1_vs_Pre1")

        Returns:
            Path to saved figure
        """
        band_names = list(all_results.keys())
        n_bands = len(band_names)

        if n_bands == 0:
            return None

        # Use non-interactive backend
        import matplotlib
        matplotlib.use('Agg')

        # Collect data for table
        table_data = []
        for band_name in band_names:
            result = all_results[band_name]
            stats = result['statistics']

            # Get t-value statistics
            t_obs = stats['t_obs']
            t_mean = np.mean(t_obs)
            t_max = np.max(t_obs)
            t_min = np.min(t_obs)

            # Get p-values
            p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else 1.0
            p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else 1.0

            # Number of significant channels
            n_sig = np.sum(stats['sig_mask'])

            # Significance stars
            min_p = min(p_pos, p_neg)
            if min_p < 0.001:
                sig_stars = '***'
            elif min_p < 0.01:
                sig_stars = '**'
            elif min_p < 0.05:
                sig_stars = '*'
            elif min_p < 0.10:
                sig_stars = '^'
            else:
                sig_stars = ''

            table_data.append([
                band_name,
                f"{result['band_range'][0]}-{result['band_range'][1]}",
                f"{t_mean:.3f}",
                f"{t_min:.3f}",
                f"{t_max:.3f}",
                f"{p_pos:.4f}" if p_pos < 1.0 else "n.s.",
                f"{p_neg:.4f}" if p_neg < 1.0 else "n.s.",
                f"{n_sig}",
                sig_stars
            ])

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 3 + 0.4 * n_bands), facecolor='white')
        ax.axis('off')

        # Title
        if comparison_name:
            title = f'Statistical Results: {comparison_name}'
        else:
            title = 'Statistical Results Summary'

        # Get group info from first result
        first_result = all_results[band_names[0]]
        subtitle = f"{first_result['group_a']} (n={first_result['n_subj_a']}) vs {first_result['group_b']} (n={first_result['n_subj_b']})"
        method = first_result['statistics'].get('method', 'unknown')
        method_label = {
            'ttest_fdr': 'Independent t-test + FDR',
            'paired_ttest_fdr': 'Paired t-test + FDR',
            'cluster_permutation': 'Cluster-based Permutation'
        }.get(method, method)

        fig.suptitle(f"{title}\n{subtitle}\nMethod: {method_label}",
                    fontsize=PUBLICATION_PARAMS['font']['title_size'],
                    fontweight='bold', y=0.98)

        # Column headers
        columns = ['Band', 'Hz', 't(mean)', 't(min)', 't(max)', 'p(+)', 'p(-)', 'Sig Ch', 'Sig']

        # Create table
        table = ax.table(
            cellText=table_data,
            colLabels=columns,
            loc='center',
            cellLoc='center',
            colWidths=[0.10, 0.08, 0.10, 0.10, 0.10, 0.12, 0.12, 0.08, 0.06]
        )

        # Style the table
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.8)

        # Style header row
        for j, col in enumerate(columns):
            cell = table[(0, j)]
            cell.set_facecolor('#2E7D32')
            cell.set_text_props(color='white', fontweight='bold')

        # Style data rows with alternating colors and significance highlighting
        for i, row_data in enumerate(table_data):
            row_idx = i + 1  # +1 because header is row 0

            # Alternating row colors
            bg_color = '#f5f5f5' if i % 2 == 0 else 'white'

            # Check significance for highlighting
            sig_stars = row_data[-1]
            if sig_stars in ['***', '**', '*']:
                bg_color = '#c8e6c9'  # Light green for significant
            elif sig_stars == '^':
                bg_color = '#fff9c4'  # Light yellow for trend

            for j in range(len(columns)):
                cell = table[(row_idx, j)]
                cell.set_facecolor(bg_color)

                # Bold the significance column
                if j == len(columns) - 1 and sig_stars:
                    cell.set_text_props(fontweight='bold')

        # Add legend
        legend_text = "Significance: *** p<0.001, ** p<0.01, * p<0.05, ^ p<0.10, n.s. = not significant"
        fig.text(0.5, 0.02, legend_text, ha='center', fontsize=9, style='italic')

        # Adjust layout
        plt.subplots_adjust(top=0.80, bottom=0.10)

        # Save
        if comparison_name:
            filename = f'{comparison_name}_statistics_table.png'
        else:
            filename = 'statistics_table.png'

        output_file = self.figures_dir / filename
        plt.savefig(output_file, dpi=PUBLICATION_PARAMS['figure']['dpi'],
                   bbox_inches='tight', facecolor='white', edgecolor='none')

        plt.close()

        # Also save as CSV for easy data access
        csv_file = self.figures_dir / filename.replace('.png', '.csv')
        with open(csv_file, 'w') as f:
            f.write(','.join(columns) + '\n')
            for row in table_data:
                f.write(','.join(row) + '\n')

        return str(output_file)

    def generate_methods_section(self, all_results: Dict, comparison_name: str = None,
                                  config: Dict = None) -> str:
        """Generate publication-ready methods section text.

        Args:
            all_results: Dictionary of band results
            comparison_name: Name of comparison (e.g., "Post1_vs_Pre1")
            config: Analysis configuration dictionary

        Returns:
            Path to saved methods text file
        """
        band_names = list(all_results.keys())
        if not band_names:
            return None

        # Get info from first result
        first_result = all_results[band_names[0]]
        stats = first_result['statistics']
        method = stats.get('method', 'cluster_permutation')
        n_a = first_result['n_subj_a']
        n_b = first_result['n_subj_b']
        group_a = first_result['group_a']
        group_b = first_result['group_b']

        # Get frequency bands info
        bands_text = []
        for band_name in band_names:
            result = all_results[band_name]
            bands_text.append(f"{band_name} ({result['band_range'][0]}-{result['band_range'][1]} Hz)")
        bands_str = ", ".join(bands_text)

        # Get config parameters
        if config:
            n_perm = config.get('n_permutations', 1000)
            cluster_alpha = config.get('cluster_alpha', 0.05)
            sig_alpha = config.get('significance_alpha', 0.05)
            epoch_length = config.get('epoch_length', 2.0)
            resample_rate = config.get('resample_rate', 256)
        else:
            n_perm = 1000
            cluster_alpha = 0.05
            sig_alpha = 0.05
            epoch_length = 2.0
            resample_rate = 256

        # Generate appropriate methods text based on statistical method used
        if method == 'cluster_permutation':
            methods_text = self._generate_cluster_methods(
                n_a, n_b, group_a, group_b, bands_str,
                n_perm, cluster_alpha, sig_alpha, epoch_length, resample_rate
            )
            method_type = "cluster_permutation"
        elif method in ['paired_ttest_fdr', 'ttest_fdr']:
            methods_text = self._generate_paired_ttest_methods(
                n_a, n_b, group_a, group_b, bands_str,
                sig_alpha, epoch_length, resample_rate
            )
            method_type = "paired_ttest_fdr"
        else:
            # Default to cluster description
            methods_text = self._generate_cluster_methods(
                n_a, n_b, group_a, group_b, bands_str,
                n_perm, cluster_alpha, sig_alpha, epoch_length, resample_rate
            )
            method_type = "cluster_permutation"

        # Save to file
        if comparison_name:
            filename = f'{comparison_name}_methods_section_{method_type}.txt'
        else:
            filename = f'methods_section_{method_type}.txt'

        output_file = self.figures_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(methods_text)

        return str(output_file)

    def _generate_cluster_methods(self, n_a: int, n_b: int, group_a: str, group_b: str,
                                   bands_str: str, n_perm: int, cluster_alpha: float,
                                   sig_alpha: float, epoch_length: float,
                                   resample_rate: int) -> str:
        """Generate methods section for cluster-based permutation testing."""

        text = """METHODS SECTION: Cluster-Based Permutation Testing
================================================================================

EEG Statistical Analysis
------------------------

Power spectral density (PSD) was computed using Welch's method with {epoch_length}-second
epochs and 50% overlap. Data were resampled to {resample_rate} Hz prior to analysis.
Frequency band power was extracted for the following bands: {bands_str}.

For each participant, the change in band power from pre- to post-intervention was
calculated (Post - Pre) for each electrode. Group differences in these change scores
were then evaluated using cluster-based permutation testing (Maris & Oostenveld, 2007),
implemented in MNE-Python (Gramfort et al., 2013).

Cluster-based permutation testing controls for multiple comparisons while maintaining
sensitivity to effects that are distributed across neighboring electrodes. The procedure
was as follows: First, independent-samples t-tests were computed at each electrode,
comparing the change scores between {group_a} (n = {n_a}) and {group_b} (n = {n_b}).
Electrodes exceeding a cluster-forming threshold of p < {cluster_alpha} were grouped
into clusters based on spatial adjacency. The sum of t-values within each cluster
served as the cluster-level test statistic.

The null distribution of cluster statistics was generated by randomly permuting group
labels {n_perm} times and recalculating the maximum cluster statistic for each
permutation. Clusters in the observed data were considered statistically significant
if their p-value (proportion of permutation statistics exceeding the observed cluster
statistic) was less than {sig_alpha}.

This non-parametric approach provides strong control of the family-wise error rate
while remaining sensitive to spatially distributed effects, making it well-suited
for high-density EEG analysis.

References
----------
Gramfort, A., Luessi, M., Larson, E., Engemann, D. A., Strohmeier, D., Brodbeck, C.,
    ... & Hämäläinen, M. (2013). MEG and EEG data analysis with MNE-Python.
    Frontiers in Neuroscience, 7, 267.

Maris, E., & Oostenveld, R. (2007). Nonparametric statistical testing of EEG- and
    MEG-data. Journal of Neuroscience Methods, 164(1), 177-190.

================================================================================
""".format(
            epoch_length=epoch_length,
            resample_rate=resample_rate,
            bands_str=bands_str,
            group_a=group_a,
            n_a=n_a,
            group_b=group_b,
            n_b=n_b,
            cluster_alpha=cluster_alpha,
            n_perm=n_perm,
            sig_alpha=sig_alpha
        )

        return text

    def _generate_paired_ttest_methods(self, n_a: int, n_b: int, group_a: str, group_b: str,
                                        bands_str: str, sig_alpha: float,
                                        epoch_length: float, resample_rate: int) -> str:
        """Generate methods section for paired t-tests with FDR correction."""

        text = """METHODS SECTION: Paired T-Tests with FDR Correction
================================================================================

EEG Statistical Analysis
------------------------

Power spectral density (PSD) was computed using Welch's method with {epoch_length}-second
epochs and 50% overlap. Data were resampled to {resample_rate} Hz prior to analysis.
Frequency band power was extracted for the following bands: {bands_str}.

For each participant, the change in band power from pre- to post-intervention was
calculated (Post - Pre) for each electrode. Due to the limited sample size
({group_a}: n = {n_a}; {group_b}: n = {n_b}), cluster-based permutation testing
was not feasible, as this method requires adequate sample sizes to generate a
reliable null distribution through permutation (Maris & Oostenveld, 2007). With
very small samples, the number of unique permutations is insufficient to estimate
p-values with adequate precision, and statistical power is severely compromised.

Therefore, group differences in change scores were evaluated using paired t-tests
at each electrode, with correction for multiple comparisons using the False
Discovery Rate (FDR) procedure (Benjamini & Hochberg, 1995). The FDR controls
the expected proportion of false positives among rejected hypotheses, providing
a balance between Type I error control and statistical power. Electrodes were
considered statistically significant at an FDR-corrected threshold of p < {sig_alpha}.

While this approach does not account for spatial dependencies between electrodes
as cluster-based methods do, it remains a valid and commonly used approach for
EEG analysis when sample sizes preclude permutation-based inference. Results
should be interpreted with appropriate caution given the limited sample size,
and replication with larger samples is recommended.

References
----------
Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate:
    A practical and powerful approach to multiple testing. Journal of the
    Royal Statistical Society: Series B (Methodological), 57(1), 289-300.

Maris, E., & Oostenveld, R. (2007). Nonparametric statistical testing of EEG-
    and MEG-data. Journal of Neuroscience Methods, 164(1), 177-190.

================================================================================
""".format(
            epoch_length=epoch_length,
            resample_rate=resample_rate,
            bands_str=bands_str,
            group_a=group_a,
            n_a=n_a,
            group_b=group_b,
            n_b=n_b,
            sig_alpha=sig_alpha
        )

        return text

    def generate_results_section(self, all_comparisons: Dict, config: Dict = None) -> str:
        """Generate a complete publication-ready results section with tables and figure references.

        Args:
            all_comparisons: Dictionary of all comparison results (e.g., {'Post1_vs_Pre1': {...}, 'Post2_vs_Pre2': {...}})
            config: Analysis configuration dictionary

        Returns:
            Path to saved results section file
        """
        if not all_comparisons:
            return None

        # Check if single comparison or multiple
        first_key = list(all_comparisons.keys())[0]
        first_val = all_comparisons[first_key]

        # Determine structure
        if 'band_name' in first_val:
            # Single comparison - wrap it
            all_comparisons = {'Analysis': all_comparisons}

        # Get config parameters
        if config:
            epoch_length = config.get('epoch_length', 2.0)
            resample_rate = config.get('resample_rate', 256)
            sig_alpha = config.get('significance_alpha', 0.05)
        else:
            epoch_length = 2.0
            resample_rate = 256
            sig_alpha = 0.05

        # Start building the results section
        lines = []
        lines.append("=" * 80)
        lines.append("RESULTS SECTION")
        lines.append("=" * 80)
        lines.append("")
        lines.append("EEG Frequency Band Analysis Results")
        lines.append("-" * 40)
        lines.append("")

        # Get sample size info from first comparison
        first_comp_name = list(all_comparisons.keys())[0]
        first_comp = all_comparisons[first_comp_name]
        first_band = list(first_comp.keys())[0]
        first_result = first_comp[first_band]

        group_a = first_result['group_a']
        group_b = first_result['group_b']
        n_a = first_result['n_subj_a']
        n_b = first_result['n_subj_b']
        method = first_result['statistics'].get('method', 'unknown')

        # Introduction paragraph
        lines.append("Spectral power changes from pre- to post-intervention were analyzed across")
        lines.append(f"five frequency bands: Delta (1-4 Hz), Theta (4-8 Hz), Alpha (8-13 Hz),")
        lines.append(f"Beta (13-30 Hz), and Gamma (30-45 Hz). Group differences in these change")
        lines.append(f"scores were compared between {group_a} (n = {n_a}) and {group_b} (n = {n_b}).")
        lines.append("")

        # Method note
        if method in ['paired_ttest_fdr', 'ttest_fdr']:
            lines.append("Due to limited sample sizes, paired t-tests with FDR correction were used")
            lines.append("for statistical inference (see Methods section for details).")
        else:
            lines.append("Cluster-based permutation testing was used for statistical inference")
            lines.append("(see Methods section for details).")
        lines.append("")

        # Process each comparison
        for comp_idx, (comp_name, band_results) in enumerate(all_comparisons.items()):
            # Parse comparison name for session info
            if '_vs_' in comp_name:
                parts = comp_name.split('_vs_')
                post_session = parts[0]
                pre_session = parts[1]
                session_label = f"{post_session} vs {pre_session}"
            else:
                session_label = comp_name
                post_session = "Post"
                pre_session = "Pre"

            lines.append("")
            lines.append(f"{'='*80}")
            lines.append(f"Session Comparison: {session_label}")
            lines.append(f"{'='*80}")
            lines.append("")

            # Collect statistics for table
            table_data = []
            significant_findings = []

            for band_name, result in band_results.items():
                stats = result['statistics']
                t_obs = stats['t_obs']

                # Get statistics
                t_mean = np.mean(t_obs)
                t_max = np.max(t_obs)
                t_min = np.min(t_obs)
                n_sig = np.sum(stats['sig_mask'])

                # Get p-values
                p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else None
                p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else None

                # Determine minimum p and direction
                if p_pos is not None and p_neg is not None:
                    if p_pos <= p_neg:
                        min_p = p_pos
                        direction = "positive"
                    else:
                        min_p = p_neg
                        direction = "negative"
                elif p_pos is not None:
                    min_p = p_pos
                    direction = "positive"
                elif p_neg is not None:
                    min_p = p_neg
                    direction = "negative"
                else:
                    min_p = None
                    direction = None

                # Significance stars
                if min_p is not None:
                    if min_p < 0.001:
                        sig_str = "***"
                    elif min_p < 0.01:
                        sig_str = "**"
                    elif min_p < 0.05:
                        sig_str = "*"
                    elif min_p < 0.10:
                        sig_str = "^"
                    else:
                        sig_str = ""
                else:
                    sig_str = ""

                table_data.append({
                    'band': band_name,
                    'range': f"{result['band_range'][0]}-{result['band_range'][1]}",
                    't_mean': t_mean,
                    't_min': t_min,
                    't_max': t_max,
                    'p_pos': p_pos,
                    'p_neg': p_neg,
                    'min_p': min_p,
                    'direction': direction,
                    'n_sig': n_sig,
                    'sig_str': sig_str
                })

                # Track significant findings
                if min_p is not None and min_p < 0.05:
                    significant_findings.append({
                        'band': band_name,
                        'range': result['band_range'],
                        'p': min_p,
                        'direction': direction,
                        'n_channels': n_sig,
                        't_max': t_max if direction == "positive" else t_min,
                        'sig_str': sig_str
                    })

            # Write table
            lines.append(f"Table: Statistical Results for {session_label}")
            lines.append("-" * 80)
            lines.append(f"{'Band':<10} {'Hz':<8} {'t(mean)':<10} {'t(min)':<10} {'t(max)':<10} {'p-value':<12} {'Sig Ch':<8} {'Sig':<5}")
            lines.append("-" * 80)

            for row in table_data:
                if row['min_p'] is not None:
                    p_str = f"{row['min_p']:.4f}"
                else:
                    p_str = "n.s."

                lines.append(f"{row['band']:<10} {row['range']:<8} {row['t_mean']:<10.3f} {row['t_min']:<10.3f} {row['t_max']:<10.3f} {p_str:<12} {row['n_sig']:<8} {row['sig_str']:<5}")

            lines.append("-" * 80)
            lines.append("Note: * p < .05, ** p < .01, *** p < .001, ^ p < .10 (trend)")
            lines.append(f"Sig Ch = Number of electrodes showing significant effects (p < {sig_alpha})")
            lines.append("")

            # Write narrative results
            lines.append("")
            lines.append(f"Narrative Results: {session_label}")
            lines.append("-" * 40)
            lines.append("")

            if significant_findings:
                lines.append(f"Analysis of the {session_label} comparison revealed significant group")
                lines.append(f"differences in {len(significant_findings)} frequency band(s):")
                lines.append("")

                for finding in significant_findings:
                    band_range_str = f"{finding['range'][0]}-{finding['range'][1]} Hz"
                    direction_word = "greater" if finding['direction'] == "positive" else "reduced"

                    if finding['p'] < 0.001:
                        p_report = "p < .001"
                    else:
                        p_report = f"p = {finding['p']:.3f}"

                    lines.append(f"  {finding['band']} Band ({band_range_str}):")
                    lines.append(f"    A significant group difference was observed ({p_report}), with")
                    lines.append(f"    {group_a} showing {direction_word} power change relative to {group_b}.")
                    lines.append(f"    This effect was evident across {finding['n_channels']} electrode(s),")
                    lines.append(f"    with a maximum t-value of {abs(finding['t_max']):.2f}.")
                    lines.append("")
            else:
                lines.append(f"No statistically significant group differences were observed in any")
                lines.append(f"frequency band for the {session_label} comparison (all p > {sig_alpha}).")
                lines.append("")

            # Figure references
            lines.append("")
            lines.append(f"Figure References: {session_label}")
            lines.append("-" * 40)
            lines.append(f"  - Topographic maps: See Figure {comp_name}_summary.png")
            lines.append(f"  - Statistical table: See {comp_name}_statistics_table.png")
            for band_name in band_results.keys():
                lines.append(f"  - {band_name} band detail: See {comp_name}_topo_{band_name}.png")
            lines.append("")

        # Summary across comparisons (if multiple)
        if len(all_comparisons) > 1:
            lines.append("")
            lines.append("=" * 80)
            lines.append("Summary Across Session Comparisons")
            lines.append("=" * 80)
            lines.append("")

            # Create comparison summary table
            lines.append("Table: Significant Findings Across All Comparisons")
            lines.append("-" * 80)
            lines.append(f"{'Comparison':<20} {'Band':<10} {'p-value':<12} {'Direction':<12} {'Channels':<10}")
            lines.append("-" * 80)

            any_significant = False
            for comp_name, band_results in all_comparisons.items():
                for band_name, result in band_results.items():
                    stats = result['statistics']
                    p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else None
                    p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else None

                    if p_pos is not None and p_pos < 0.05:
                        any_significant = True
                        n_sig = np.sum(stats['sig_mask'])
                        lines.append(f"{comp_name:<20} {band_name:<10} {p_pos:<12.4f} {'Positive':<12} {n_sig:<10}")
                    if p_neg is not None and p_neg < 0.05:
                        any_significant = True
                        n_sig = np.sum(stats['sig_mask'])
                        lines.append(f"{comp_name:<20} {band_name:<10} {p_neg:<12.4f} {'Negative':<12} {n_sig:<10}")

            if not any_significant:
                lines.append("No significant findings across any comparison.")

            lines.append("-" * 80)
            lines.append("")

            # Narrative summary
            lines.append("")
            lines.append("Interpretation:")
            lines.append("-" * 40)

            # Collect all significant bands per comparison
            comp_summaries = {}
            for comp_name, band_results in all_comparisons.items():
                sig_bands = []
                for band_name, result in band_results.items():
                    stats = result['statistics']
                    p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else 1.0
                    p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else 1.0
                    if min(p_pos, p_neg) < 0.05:
                        sig_bands.append(band_name)
                comp_summaries[comp_name] = sig_bands

            lines.append("")
            for comp_name, sig_bands in comp_summaries.items():
                if sig_bands:
                    bands_str = ", ".join(sig_bands)
                    lines.append(f"  {comp_name}: Significant effects in {bands_str}")
                else:
                    lines.append(f"  {comp_name}: No significant effects")
            lines.append("")

        # Footer
        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF RESULTS SECTION")
        lines.append("=" * 80)
        lines.append("")
        lines.append("Note: This results section was automatically generated. Please review and")
        lines.append("edit as needed for your specific publication requirements.")
        lines.append("")

        # Write to file
        output_file = self.figures_dir / 'RESULTS_SECTION.txt'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # Also create a formatted version with markdown
        md_lines = self._convert_results_to_markdown(lines, all_comparisons)
        md_file = self.figures_dir / 'RESULTS_SECTION.md'
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))

        return str(output_file)

    def _convert_results_to_markdown(self, text_lines: List[str], all_comparisons: Dict) -> List[str]:
        """Convert results section to markdown format with embedded images."""
        md = []
        md.append("# Results")
        md.append("")

        # Get basic info
        first_comp_name = list(all_comparisons.keys())[0]
        first_comp = all_comparisons[first_comp_name]
        first_band = list(first_comp.keys())[0]
        first_result = first_comp[first_band]
        group_a = first_result['group_a']
        group_b = first_result['group_b']
        n_a = first_result['n_subj_a']
        n_b = first_result['n_subj_b']
        method = first_result['statistics'].get('method', 'unknown')

        md.append("## EEG Frequency Band Analysis")
        md.append("")
        md.append(f"Spectral power changes from pre- to post-intervention were analyzed across five frequency bands: Delta (1-4 Hz), Theta (4-8 Hz), Alpha (8-13 Hz), Beta (13-30 Hz), and Gamma (30-45 Hz). Group differences in these change scores were compared between **{group_a}** (n = {n_a}) and **{group_b}** (n = {n_b}).")
        md.append("")

        if method in ['paired_ttest_fdr', 'ttest_fdr']:
            md.append("*Due to limited sample sizes, paired t-tests with FDR correction were used for statistical inference (see Methods section for details).*")
        else:
            md.append("*Cluster-based permutation testing was used for statistical inference (see Methods section for details).*")
        md.append("")

        # Process each comparison
        for comp_idx, (comp_name, band_results) in enumerate(all_comparisons.items()):
            if '_vs_' in comp_name:
                parts = comp_name.split('_vs_')
                session_label = f"{parts[0]} vs {parts[1]}"
            else:
                session_label = comp_name

            md.append(f"## {session_label}")
            md.append("")

            # Summary figure
            md.append(f"### Topographic Summary")
            md.append("")
            md.append(f"![{comp_name} Summary]({comp_name}_summary.png)")
            md.append("")
            md.append(f"*Figure: Topographic maps showing power changes (Post - Pre) for {group_a} (top row), {group_b} (middle row), and group differences (bottom row) across all frequency bands.*")
            md.append("")

            # Statistics table
            md.append(f"### Statistical Results")
            md.append("")
            md.append(f"![{comp_name} Statistics Table]({comp_name}_statistics_table.png)")
            md.append("")

            # Also include text table for accessibility
            md.append("| Band | Hz | t(mean) | t(min) | t(max) | p-value | Sig Channels |")
            md.append("|------|-----|---------|--------|--------|---------|--------------|")

            significant_findings = []
            for band_name, result in band_results.items():
                stats = result['statistics']
                t_obs = stats['t_obs']
                t_mean = np.mean(t_obs)
                t_max = np.max(t_obs)
                t_min = np.min(t_obs)
                n_sig = np.sum(stats['sig_mask'])

                p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else None
                p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else None

                if p_pos is not None and p_neg is not None:
                    min_p = min(p_pos, p_neg)
                    direction = "positive" if p_pos <= p_neg else "negative"
                elif p_pos is not None:
                    min_p = p_pos
                    direction = "positive"
                elif p_neg is not None:
                    min_p = p_neg
                    direction = "negative"
                else:
                    min_p = None
                    direction = None

                if min_p is not None:
                    if min_p < 0.001:
                        p_str = "< .001***"
                    elif min_p < 0.01:
                        p_str = f"{min_p:.3f}**"
                    elif min_p < 0.05:
                        p_str = f"{min_p:.3f}*"
                    else:
                        p_str = f"{min_p:.3f}"
                else:
                    p_str = "n.s."

                band_range = f"{result['band_range'][0]}-{result['band_range'][1]}"
                md.append(f"| {band_name} | {band_range} | {t_mean:.3f} | {t_min:.3f} | {t_max:.3f} | {p_str} | {n_sig} |")

                if min_p is not None and min_p < 0.05:
                    significant_findings.append({
                        'band': band_name,
                        'range': result['band_range'],
                        'p': min_p,
                        'direction': direction,
                        'n_channels': n_sig,
                        't_max': t_max if direction == "positive" else t_min
                    })

            md.append("")
            md.append("*Note: \\* p < .05, \\*\\* p < .01, \\*\\*\\* p < .001*")
            md.append("")

            # Narrative
            md.append("### Key Findings")
            md.append("")

            if significant_findings:
                for finding in significant_findings:
                    band_range_str = f"{finding['range'][0]}-{finding['range'][1]} Hz"
                    direction_word = "greater" if finding['direction'] == "positive" else "reduced"

                    if finding['p'] < 0.001:
                        p_report = "p < .001"
                    else:
                        p_report = f"p = {finding['p']:.3f}"

                    md.append(f"**{finding['band']} Band ({band_range_str}):** A significant group difference was observed ({p_report}), with {group_a} showing {direction_word} power change relative to {group_b}. This effect was evident across {finding['n_channels']} electrode(s), with a maximum t-value of {abs(finding['t_max']):.2f}.")
                    md.append("")
            else:
                md.append(f"No statistically significant group differences were observed in any frequency band for the {session_label} comparison (all p > .05).")
                md.append("")

        # Summary table if multiple comparisons
        if len(all_comparisons) > 1:
            md.append("## Summary Across Comparisons")
            md.append("")
            md.append("| Comparison | Significant Bands |")
            md.append("|------------|-------------------|")

            for comp_name, band_results in all_comparisons.items():
                sig_bands = []
                for band_name, result in band_results.items():
                    stats = result['statistics']
                    p_pos = stats['positive_clusters'][0]['pval'] if stats['positive_clusters'] else 1.0
                    p_neg = stats['negative_clusters'][0]['pval'] if stats['negative_clusters'] else 1.0
                    if min(p_pos, p_neg) < 0.05:
                        sig_bands.append(band_name)

                if sig_bands:
                    md.append(f"| {comp_name} | {', '.join(sig_bands)} |")
                else:
                    md.append(f"| {comp_name} | None |")

            md.append("")

        md.append("---")
        md.append("*This results section was automatically generated. Please review and edit as needed for your specific publication requirements.*")

        return md

    def save_comparison_report(self, matlab_results: Optional[Dict], 
                               python_results: Dict, output_file: Path):
        """Create comparison report between MATLAB and Python results"""
        
        with open(output_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("  MATLAB vs Python Results Comparison\n")
            f.write("=" * 70 + "\n\n")
            
            if matlab_results is None:
                f.write("MATLAB results not available for comparison.\n\n")
            else:
                f.write("Comparing p-values across frequency bands:\n\n")
                f.write(f"{'Band':<10} {'MATLAB p+':<15} {'Python p+':<15} {'Difference':<15}\n")
                f.write("-" * 70 + "\n")
                
                for band_name in FREQUENCY_BANDS.keys():
                    if band_name in python_results:
                        py_stats = python_results[band_name]['statistics']
                        py_p = py_stats['positive_clusters'][0]['pval'] if py_stats['positive_clusters'] else 1.0
                        
                        mat_p = matlab_results.get(band_name, {}).get('p_pos', 1.0)
                        
                        diff = abs(py_p - mat_p)
                        
                        f.write(f"{band_name:<10} {mat_p:<15.4f} {py_p:<15.4f} {diff:<15.4f}\n")
            
            f.write("\n" + "=" * 70 + "\n")
            f.write("Python Analysis Summary:\n")
            f.write("=" * 70 + "\n\n")
            
            for band_name, result in python_results.items():
                f.write(f"\n{band_name} Band:\n")
                f.write(f"  Group A (n={result['n_subj_a']}): ")
                f.write(f"mean={np.mean(result['ga_diff_a']):.4f}, ")
                f.write(f"range=[{np.min(result['ga_diff_a']):.4f}, {np.max(result['ga_diff_a']):.4f}]\n")
                
                f.write(f"  Group B (n={result['n_subj_b']}): ")
                f.write(f"mean={np.mean(result['ga_diff_b']):.4f}, ")
                f.write(f"range=[{np.min(result['ga_diff_b']):.4f}, {np.max(result['ga_diff_b']):.4f}]\n")
                
                stats = result['statistics']
                if stats['positive_clusters']:
                    f.write(f"  Positive clusters: p={stats['positive_clusters'][0]['pval']:.4f}\n")
                if stats['negative_clusters']:
                    f.write(f"  Negative clusters: p={stats['negative_clusters'][0]['pval']:.4f}\n")
                if not stats['positive_clusters'] and not stats['negative_clusters']:
                    f.write(f"  No significant clusters\n")
