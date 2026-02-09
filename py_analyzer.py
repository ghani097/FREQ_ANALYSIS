"""
Core analysis engine for EEG frequency analysis with cluster-based permutation testing
"""

import numpy as np
import mne
from mne.time_frequency import psd_array_welch
from mne.stats import permutation_cluster_test
from scipy import stats
from scipy.stats import ttest_ind, ttest_rel, false_discovery_control
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
import warnings

from py_config import FREQUENCY_BANDS, DEFAULT_PARAMS
from py_data_loader import EEGDataLoader


class FrequencyAnalyzer:
    """Main analysis engine using MNE-Python"""
    
    def __init__(self, config: Dict, progress_callback: Optional[Callable] = None):
        self.config = config
        self.progress = progress_callback or print
        self.loader = EEGDataLoader(config['root_dir'])
        
        # Store results
        self.results = {}
        self.grand_averages = {}
        
    def run_analysis(self):
        """Run complete analysis pipeline"""
        
        self.progress("=== Starting EEG Frequency Analysis ===")
        
        # Step 1: Load data
        self.progress("Step 1: Loading and processing data...")
        group_data = self._load_all_data()
        
        if not group_data:
            raise ValueError("Failed to load data")
        
        # Step 2: Get Pre/Post sessions and pair them
        pre_sessions = sorted([s for s in self.config['sessions'] if 'pre' in s.lower()])
        post_sessions = sorted([s for s in self.config['sessions'] if 'post' in s.lower()])
        
        if not pre_sessions or not post_sessions:
            raise ValueError("Need both Pre and Post sessions")
        
        # Check if user wants single session pair or all pairs
        process_all_pairs = self.config.get('process_all_session_pairs', True)
        
        if process_all_pairs and len(pre_sessions) > 1 and len(post_sessions) > 1:
            # Process all Pre/Post pairs (Pre1/Post1, Pre2/Post2, etc.)
            session_pairs = list(zip(pre_sessions, post_sessions))
            self.progress(f"Found {len(session_pairs)} session pairs to analyze")
        else:
            # Process only first pair (backward compatibility)
            session_pairs = [(pre_sessions[0], post_sessions[0])]
        
        # Step 3: Process each session pair
        all_results = {}
        
        for pre_session, post_session in session_pairs:
            comparison_name = f"{post_session}_vs_{pre_session}"
            self.progress(f"\n{'='*60}")
            self.progress(f"Comparing: {post_session} vs {pre_session}")
            self.progress(f"{'='*60}")
            
            # Process each frequency band for this comparison
            self.progress("Analyzing frequency bands...")
            pair_results = {}
            
            for band_name, band_range in FREQUENCY_BANDS.items():
                self.progress(f"  Processing {band_name} band ({band_range[0]}-{band_range[1]} Hz)...")
                
                try:
                    result = self._analyze_band(
                        group_data, 
                        band_name, 
                        band_range,
                        pre_session,
                        post_session
                    )
                    
                    if result:
                        pair_results[band_name] = result
                        self.progress(f"    ✓ {band_name} complete")
                        self._print_statistics(result, band_name)
                        
                except Exception as e:
                    self.progress(f"    ✗ {band_name} failed: {str(e)}")
            
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

        # Scan directory
        scan_info = self.loader.scan_directory()
        self.progress(f"  Found {scan_info['total_files']} .set files")
        self.progress(f"  Groups: {', '.join(scan_info['groups'])}")
        self.progress(f"  Sessions: {', '.join(scan_info['sessions'])}")

        # Get ALL Pre/Post sessions
        pre_sessions = sorted([s for s in scan_info['sessions'] if 'pre' in s.lower()])
        post_sessions = sorted([s for s in scan_info['sessions'] if 'post' in s.lower()])

        if not pre_sessions or not post_sessions:
            raise ValueError("Need both Pre and Post sessions")

        self.progress(f"  Pre sessions to load: {pre_sessions}")
        self.progress(f"  Post sessions to load: {post_sessions}")

        # Load data for each group, organized by session
        # Structure: group_data[group][session] = {'subjects': [...], 'data': [...]}
        group_data = {}

        for group in scan_info['groups']:
            group_data[group] = {}

            # Load ALL sessions for this group
            all_sessions = pre_sessions + post_sessions

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
                for subj in subjects:
                    try:
                        filepath = session_path / f"{subj}.set"
                        raw = self.loader.load_set_file(
                            filepath,
                            self.config.get('resample_rate', 256)
                        )

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
    
    def _compute_psd(self, raw: mne.io.Raw) -> Optional[Dict]:
        """Compute power spectral density"""
        
        try:
            # Get data
            data = raw.get_data()
            sfreq = raw.info['sfreq']
            
            # Compute PSD using Welch method
            freq_range = self.config.get('freq_range', (1, 45))
            n_fft = int(self.config.get('epoch_length', 2.0) * sfreq)
            
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
                'ch_names': raw.ch_names,
                'info': raw.info
            }
            
        except Exception as e:
            self.progress(f"      PSD computation failed: {str(e)}")
            return None
    
    def _analyze_band(self, group_data: Dict, band_name: str, band_range: Tuple,
                     pre_session: str, post_session: str) -> Optional[Dict]:
        """Analyze one frequency band for a specific Pre/Post session pair"""

        # Get groups
        groups = list(group_data.keys())
        if len(groups) < 2:
            return None

        group_a, group_b = groups[0], groups[1]

        self.progress(f"    Analyzing {band_name}: {post_session} vs {pre_session}")

        # Get matched subjects for this specific session pair
        pre_data_a, post_data_a = self._get_matched_session_data(
            group_data[group_a], pre_session, post_session
        )
        pre_data_b, post_data_b = self._get_matched_session_data(
            group_data[group_b], pre_session, post_session
        )

        if not pre_data_a or not post_data_a:
            self.progress(f"      WARNING: No matched data for {group_a} in {pre_session}/{post_session}")
            return None
        if not pre_data_b or not post_data_b:
            self.progress(f"      WARNING: No matched data for {group_b} in {pre_session}/{post_session}")
            return None

        # Extract band power and compute differences
        diff_a = self._compute_band_differences(pre_data_a, post_data_a, band_range)
        diff_b = self._compute_band_differences(pre_data_b, post_data_b, band_range)
        
        if diff_a is None or diff_b is None:
            return None
        
        # CHECK SAMPLE SIZE
        n_a, n_b = len(diff_a), len(diff_b)
        self.progress(f"    Sample sizes: {group_a}={n_a}, {group_b}={n_b}")
        
        if n_a < 5 or n_b < 5:
            self.progress(f"    ⚠️  CRITICAL WARNING: Sample size too small!")
            self.progress(f"    ⚠️  Minimum recommended: 5 subjects per group")
            self.progress(f"    ⚠️  Statistical power is very low - results unreliable")
            if n_b < 3:
                self.progress(f"    ⚠️  Group {group_b} (n={n_b}) is CRITICALLY underpowered")
                self.progress(f"    ⚠️  With n<3, permutation testing essentially fails")
                self.progress(f"    ⚠️  P-values will default to 1 (no significance possible)")
        
        # Compute grand averages
        ga_diff_a = np.mean(diff_a, axis=0)
        ga_diff_b = np.mean(diff_b, axis=0)
        ga_a_vs_b = ga_diff_a - ga_diff_b
        
        # Diagnostic check
        mean_diff = np.mean(np.abs(ga_diff_a - ga_diff_b))
        max_diff = np.max(np.abs(ga_diff_a - ga_diff_b))
        
        if mean_diff < 1e-10:
            self.progress(f"    ⚠️ WARNING: Groups appear IDENTICAL (diff={mean_diff:.2e})")
        else:
            self.progress(f"    ✓ Group difference: mean={mean_diff:.2e}, max={max_diff:.2e}")
        
        # Run cluster-based permutation test
        stat_result = self._run_cluster_test(diff_a, diff_b)

        # Get channel info from first subject (from pre_data_a which we already extracted)
        ch_names = pre_data_a[0]['ch_names']
        info = pre_data_a[0]['info']

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
            'statistics': stat_result,
            'ch_names': ch_names,
            'info': info,
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
                                  band_range: Tuple) -> Optional[np.ndarray]:
        """Compute Post-Pre difference for a frequency band"""
        
        if not pre_data or not post_data or len(pre_data) != len(post_data):
            return None
        
        differences = []
        
        for pre, post in zip(pre_data, post_data):
            # Get frequency indices for band
            freq_mask = (pre['freqs'] >= band_range[0]) & (pre['freqs'] <= band_range[1])
            
            # Average power in band
            band_power_pre = np.mean(pre['psds'][:, freq_mask], axis=1)
            band_power_post = np.mean(post['psds'][:, freq_mask], axis=1)
            
            # Compute difference
            diff = band_power_post - band_power_pre
            differences.append(diff)
        
        return np.array(differences)
    
    def _run_cluster_test(self, data_a: np.ndarray, data_b: np.ndarray) -> Dict:
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
        
        # DECISION LOGIC
        if method == 'auto':
            # Automatic selection
            if small_sample:
                self.progress(f"      ⚠️ Small sample detected (n_a={n_a}, n_b={n_b})")
                self.progress(f"      → Auto: Using independent t-tests with FDR correction")
                return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=False)
            else:
                self.progress(f"      → Auto: Using cluster-based permutation test")
                return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha, sig_alpha, tail)
        
        elif method == 'cluster':
            # Force cluster permutation
            if small_sample:
                self.progress(f"      ⚠️ Small sample (n_a={n_a}, n_b={n_b}) but forcing cluster test")
            self.progress(f"      → Using cluster-based permutation test")
            return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha, sig_alpha, tail)
        
        elif method == 'paired_ttest':
            # Paired t-test + FDR
            self.progress(f"      → Using PAIRED t-tests with FDR correction")
            return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=True)
        
        elif method == 'independent_ttest':
            # Independent t-test + FDR
            self.progress(f"      → Using INDEPENDENT t-tests with FDR correction")
            return self._run_ttest_fallback(data_a, data_b, sig_alpha, paired=False)
        
        else:
            # Fallback to cluster
            self.progress(f"      → Unknown method, using cluster permutation")
            return self._run_cluster_permutation(data_a, data_b, n_perm, cluster_alpha, sig_alpha, tail)
    
    def _run_cluster_permutation(self, data_a: np.ndarray, data_b: np.ndarray,
                                  n_perm: int, cluster_alpha: float, 
                                  sig_alpha: float, tail: int) -> Dict:
        """Standard cluster-based permutation test"""
        
        # For two-tailed test
        if tail == 0:
            alpha = sig_alpha / 2
        else:
            alpha = sig_alpha
        
        # Simple threshold-based clustering (no spatial neighbors for now)
        # We'll use channel-wise t-tests
        threshold = stats.t.ppf(1 - cluster_alpha, data_a.shape[0] + data_b.shape[0] - 2)
        
        try:
            # Permutation test
            t_obs, clusters, cluster_pv, H0 = permutation_cluster_test(
                [data_a, data_b],
                n_permutations=n_perm,
                threshold=threshold,
                tail=tail,
                n_jobs=self.config.get('n_jobs', -1),
                verbose=False
            )
            
            # Find significant clusters
            sig_clusters_pos = []
            sig_clusters_neg = []
            
            if len(clusters) > 0 and len(cluster_pv) > 0:
                for idx, (cluster, pval) in enumerate(zip(clusters, cluster_pv)):
                    cluster_channels = np.where(cluster)[0]
                    
                    if len(cluster_channels) > 0:
                        cluster_info = {
                            'channels': cluster_channels.tolist(),
                            'pval': float(pval),
                            't_values': t_obs[cluster_channels].tolist()
                        }
                        
                        # Determine if positive or negative cluster
                        if np.mean(t_obs[cluster_channels]) > 0:
                            sig_clusters_pos.append(cluster_info)
                        else:
                            sig_clusters_neg.append(cluster_info)
            
            # Sort by p-value
            sig_clusters_pos.sort(key=lambda x: x['pval'])
            sig_clusters_neg.sort(key=lambda x: x['pval'])
            
            # Create mask for significant channels
            sig_mask = np.zeros(len(t_obs), dtype=bool)
            for cluster_info in sig_clusters_pos + sig_clusters_neg:
                if cluster_info['pval'] < sig_alpha:
                    sig_mask[cluster_info['channels']] = True
            
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
            # Return dummy results
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
    
    def _run_ttest_fallback(self, data_a: np.ndarray, data_b: np.ndarray, 
                            sig_alpha: float = 0.05, paired: bool = False) -> Dict:
        """Channel-wise t-tests with FDR correction (paired or independent)"""
        
        n_channels = data_a.shape[1]
        t_obs = np.zeros(n_channels)
        p_values = np.zeros(n_channels)
        
        # Check if paired test is possible
        if paired and len(data_a) != len(data_b):
            self.progress(f"      ⚠️ Cannot do paired test: n_a={len(data_a)} != n_b={len(data_b)}")
            self.progress(f"      → Switching to independent t-test")
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
            self.progress(f"      ⚠️ Using RAW p-values (FDR correction skipped)")
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
            self.progress(f"      ✓ Found {n_sig} significant channels ({test_type}, FDR-corrected)")
            min_p = np.min(p_corrected[sig_mask])
            self.progress(f"      ✓ Minimum p-value: {min_p:.4f}")
        else:
            self.progress(f"      → No significant channels ({test_type}, FDR-corrected)")
        
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
        """Print statistical results"""
        
        stats = result['statistics']
        
        if stats['positive_clusters']:
            p = stats['positive_clusters'][0]['pval']
            self.progress(f"      Positive clusters: best p={p:.4f}")
        
        if stats['negative_clusters']:
            p = stats['negative_clusters'][0]['pval']
            self.progress(f"      Negative clusters: best p={p:.4f}")
        
        if not stats['positive_clusters'] and not stats['negative_clusters']:
            self.progress(f"      No significant clusters found")
