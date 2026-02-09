"""
Check if Post1 vs Post2 data is actually different
"""

import numpy as np
from pathlib import Path
from py_data_loader import EEGDataLoader

def check_post1_vs_post2():
    """Compare data from Post1 and Post2 sessions"""
    
    print("="*80)
    print("CHECKING: Post1 vs Post2 Data Differences")
    print("="*80)
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    
    # Check GroupA SUB1 in both Post1 and Post2
    print("\n[GroupA - SUB1]")
    
    # Load Post1 Adjustment1
    post1_file = root_dir / 'GroupA' / 'Post1' / 'SUB1Adjustment1_cleaned.set'
    print(f"\nPost1 (Adjustment1): {post1_file.name}")
    if post1_file.exists():
        raw1 = loader.load_set_file(post1_file, resample_rate=256)
        data1 = raw1.get_data()
        print(f"  Shape: {data1.shape}")
        print(f"  Mean: {np.mean(data1):.6e}")
        print(f"  Std: {np.std(data1):.6e}")
        print(f"  Range: [{np.min(data1):.6e}, {np.max(data1):.6e}]")
        sample1 = data1[:5, :100]  # First 5 channels, 100 samples
    
    # Load Post2 Adjustment2
    post2_file = root_dir / 'GroupA' / 'Post2' / 'SUB1Adjustment2_cleaned.set'
    print(f"\nPost2 (Adjustment2): {post2_file.name}")
    if post2_file.exists():
        raw2 = loader.load_set_file(post2_file, resample_rate=256)
        data2 = raw2.get_data()
        print(f"  Shape: {data2.shape}")
        print(f"  Mean: {np.mean(data2):.6e}")
        print(f"  Std: {np.std(data2):.6e}")
        print(f"  Range: [{np.min(data2):.6e}, {np.max(data2):.6e}]")
        sample2 = data2[:5, :100]
    
    # Compare
    print(f"\n[COMPARISON]")
    if post1_file.exists() and post2_file.exists():
        diff = np.abs(sample1 - sample2)
        print(f"Sample difference (first 5 ch, 100 samples):")
        print(f"  Max: {np.max(diff):.6e}")
        print(f"  Mean: {np.mean(diff):.6e}")
        
        if np.max(diff) < 1e-10:
            print(f"\n  🔴 WARNING: Post1 and Post2 appear IDENTICAL!")
        else:
            print(f"\n  ✓ Post1 and Post2 are DIFFERENT")
    
    # Check Pre1 vs Pre2 as well
    print("\n" + "="*80)
    print("[GroupA - SUB1 - Pre sessions]")
    print("="*80)
    
    pre1_file = root_dir / 'GroupA' / 'Pre1' / 'SUB1Adjustment1_cleaned.set'
    pre2_file = root_dir / 'GroupA' / 'Pre2' / 'SUB1Adjustment2_cleaned.set'
    
    print(f"\nPre1 (Adjustment1): {pre1_file.name}")
    if pre1_file.exists():
        raw_pre1 = loader.load_set_file(pre1_file, resample_rate=256)
        data_pre1 = raw_pre1.get_data()
        print(f"  Shape: {data_pre1.shape}")
        print(f"  Mean: {np.mean(data_pre1):.6e}")
        sample_pre1 = data_pre1[:5, :100]
    
    print(f"\nPre2 (Adjustment2): {pre2_file.name}")
    if pre2_file.exists():
        raw_pre2 = loader.load_set_file(pre2_file, resample_rate=256)
        data_pre2 = raw_pre2.get_data()
        print(f"  Shape: {data_pre2.shape}")
        print(f"  Mean: {np.mean(data_pre2):.6e}")
        sample_pre2 = data_pre2[:5, :100]
    
    print(f"\n[COMPARISON]")
    if pre1_file.exists() and pre2_file.exists():
        diff_pre = np.abs(sample_pre1 - sample_pre2)
        print(f"Sample difference:")
        print(f"  Max: {np.max(diff_pre):.6e}")
        print(f"  Mean: {np.mean(diff_pre):.6e}")
        
        if np.max(diff_pre) < 1e-10:
            print(f"\n  🔴 WARNING: Pre1 and Pre2 appear IDENTICAL!")
        else:
            print(f"\n  ✓ Pre1 and Pre2 are DIFFERENT")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    check_post1_vs_post2()
