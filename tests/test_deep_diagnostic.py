"""
Deep diagnostic: Check actual p-values and data being compared
"""

import numpy as np
from pathlib import Path
from scipy.stats import ttest_ind
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer
from py_config import DEFAULT_PARAMS, FREQUENCY_BANDS

def deep_diagnostic():
    """Check actual p-values and what data is being compared"""
    
    print("="*80)
    print("DEEP P-VALUE DIAGNOSTIC")
    print("="*80)
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    
    # Manually compute what the analyzer computes
    print("\n[STEP 1: Loading Data]")
    
    # Get matched subjects for GroupA Pre1/Post1
    matched_a = loader.get_matched_subjects('GroupA', 'Pre1', 'Post1')
    matched_b = loader.get_matched_subjects('GroupB', 'Pre1', 'Post1')
    
    print(f"GroupA subjects: {len(matched_a)} - {matched_a}")
    print(f"GroupB subjects: {len(matched_b)} - {matched_b}")
    
    # Load and compute PSD for Alpha band as example
    print("\n[STEP 2: Computing Alpha Band Power]")
    
    def compute_band_power(group, session, subjects, band_range=(8, 13)):
        """Compute band power for subjects"""
        powers = []
        
        for subj in subjects:
            file_path = root_dir / group / session / f"{subj}.set"
            if not file_path.exists():
                print(f"  ⚠️ Missing: {file_path.name}")
                continue
                
            try:
                raw = loader.load_set_file(file_path, resample_rate=256)
                data = raw.get_data()
                
                # Compute PSD
                from mne.time_frequency import psd_array_welch
                psds, freqs = psd_array_welch(
                    data, sfreq=raw.info['sfreq'],
                    fmin=band_range[0], fmax=band_range[1],
                    n_fft=512, n_overlap=256, verbose=False
                )
                
                # Average across frequencies for each channel
                band_power = np.mean(psds, axis=1)
                powers.append(band_power)
                
                print(f"  {subj}: {len(band_power)} channels, mean power = {np.mean(band_power):.4e}")
                
            except Exception as e:
                print(f"  ✗ {subj}: {str(e)}")
        
        return np.array(powers)  # shape: (n_subjects, n_channels)
    
    # GroupA
    print("\nGroupA Pre1:")
    pre_a = compute_band_power('GroupA', 'Pre1', matched_a)
    print("\nGroupA Post1:")
    post_a = compute_band_power('GroupA', 'Post1', matched_a)
    
    # GroupB
    print("\nGroupB Pre1:")
    pre_b = compute_band_power('GroupB', 'Pre1', matched_b)
    print("\nGroupB Post1:")
    post_b = compute_band_power('GroupB', 'Post1', matched_b)
    
    # Compute differences (Post - Pre)
    print("\n[STEP 3: Computing Post-Pre Differences]")
    
    diff_a = post_a - pre_a  # shape: (n_subjects, n_channels)
    diff_b = post_b - pre_b
    
    print(f"\nGroupA differences (Post-Pre):")
    print(f"  Shape: {diff_a.shape}")
    print(f"  Mean per channel: {np.mean(diff_a, axis=0)[:5]}")  # First 5 channels
    print(f"  Overall mean: {np.mean(diff_a):.4e}")
    print(f"  Overall std: {np.std(diff_a):.4e}")
    
    print(f"\nGroupB differences (Post-Pre):")
    print(f"  Shape: {diff_b.shape}")
    print(f"  Mean per channel: {np.mean(diff_b, axis=0)[:5]}")
    print(f"  Overall mean: {np.mean(diff_b):.4e}")
    print(f"  Overall std: {np.std(diff_b):.4e}")
    
    # THIS IS WHAT GETS COMPARED
    print("\n[STEP 4: Independent T-test on Differences]")
    print("\nComparing: diff_a (GroupA Post-Pre) vs diff_b (GroupB Post-Pre)")
    
    n_channels = diff_a.shape[1]
    t_values = []
    p_values = []
    
    for ch in range(min(10, n_channels)):  # Check first 10 channels
        t_stat, p_val = ttest_ind(diff_a[:, ch], diff_b[:, ch])
        t_values.append(t_stat)
        p_values.append(p_val)
        
        print(f"\nChannel {ch}:")
        print(f"  GroupA diff values: {diff_a[:, ch]}")
        print(f"  GroupB diff values: {diff_b[:, ch]}")
        print(f"  t-statistic: {t_stat:.4f}")
        print(f"  p-value: {p_val:.4f}")
        
        if p_val < 0.5:
            print(f"  ✓ WOULD BE SIGNIFICANT at p<0.5")
        else:
            print(f"  ✗ Not significant even at p<0.5")
    
    # Overall statistics
    print("\n[STEP 5: Overall P-value Statistics]")
    
    all_p_values = []
    all_t_values = []
    
    for ch in range(n_channels):
        t_stat, p_val = ttest_ind(diff_a[:, ch], diff_b[:, ch])
        all_p_values.append(p_val)
        all_t_values.append(t_stat)
    
    all_p_values = np.array(all_p_values)
    all_t_values = np.array(all_t_values)
    
    print(f"\nAll {n_channels} channels:")
    print(f"  P-values: min={np.min(all_p_values):.6f}, max={np.max(all_p_values):.6f}, mean={np.mean(all_p_values):.6f}")
    print(f"  T-values: min={np.min(all_t_values):.4f}, max={np.max(all_t_values):.4f}, mean={np.mean(all_t_values):.4f}")
    
    n_sig_05 = np.sum(all_p_values < 0.05)
    n_sig_50 = np.sum(all_p_values < 0.5)
    
    print(f"\n  Channels with p < 0.05: {n_sig_05}/{n_channels}")
    print(f"  Channels with p < 0.5: {n_sig_50}/{n_channels}")
    
    if n_sig_50 == 0:
        print("\n  🔴 PROBLEM: Even at p<0.5, NOTHING is significant!")
        print("  This suggests the groups have nearly identical Post-Pre changes")
    
    # Check if FDR might be killing everything
    print("\n[STEP 6: FDR Correction Check]")
    
    from scipy.stats import false_discovery_control
    try:
        p_corrected = false_discovery_control(all_p_values, method='bh')
        print(f"\nFDR corrected p-values:")
        print(f"  Min: {np.min(p_corrected):.6f}")
        print(f"  Max: {np.max(p_corrected):.6f}")
        print(f"  Mean: {np.mean(p_corrected):.6f}")
        
        n_sig_fdr = np.sum(p_corrected < 0.05)
        print(f"\n  Channels significant after FDR: {n_sig_fdr}/{n_channels}")
        
    except Exception as e:
        print(f"  FDR correction failed: {e}")
    
    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80)

if __name__ == '__main__':
    deep_diagnostic()
