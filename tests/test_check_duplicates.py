"""
Diagnostic: Check if Pre/Post files are identical or duplicates
"""

import hashlib
from pathlib import Path
import numpy as np
from py_data_loader import EEGDataLoader

def get_file_hash(filepath):
    """Get MD5 hash of file"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def check_duplicate_files():
    """Check if Pre and Post files are duplicates"""
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    
    print("="*80)
    print("CHECKING FOR DUPLICATE PRE/POST FILES")
    print("="*80)
    
    groups = ['GroupA', 'GroupB']
    session_pairs = [('Pre1', 'Post1'), ('Pre2', 'Post2')]
    
    for group in groups:
        print(f"\n[{group}]")
        
        for pre_session, post_session in session_pairs:
            print(f"\n  Comparing {pre_session} vs {post_session}:")
            
            pre_dir = root_dir / group / pre_session
            post_dir = root_dir / group / post_session
            
            if not pre_dir.exists() or not post_dir.exists():
                print(f"    ⚠️ One or both directories not found")
                continue
            
            pre_files = sorted(list(pre_dir.glob("*.set")))
            post_files = sorted(list(post_dir.glob("*.set")))
            
            print(f"    {pre_session}: {len(pre_files)} files")
            print(f"    {post_session}: {len(post_files)} files")
            
            # Check each file pair
            for pre_file in pre_files:
                # Find matching post file (same subject)
                subject_name = pre_file.name
                post_file = post_dir / subject_name
                
                if post_file.exists():
                    # Compare file sizes
                    pre_size = pre_file.stat().st_size
                    post_size = post_file.stat().st_size
                    
                    if pre_size == post_size:
                        # Same size - check hash
                        pre_hash = get_file_hash(pre_file)
                        post_hash = get_file_hash(post_file)
                        
                        if pre_hash == post_hash:
                            print(f"    🔴 DUPLICATE: {subject_name}")
                            print(f"       {pre_session} and {post_session} are IDENTICAL files!")
                        else:
                            print(f"    ✓ {subject_name}: Different content (same size)")
                    else:
                        size_diff_pct = abs(pre_size - post_size) / pre_size * 100
                        print(f"    ✓ {subject_name}: Different sizes ({size_diff_pct:.1f}% diff)")
                else:
                    print(f"    ⚠️ {subject_name}: No matching {post_session} file")
    
    print("\n" + "="*80)

def check_data_content_differences():
    """Load and compare actual data values"""
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    
    print("\n" + "="*80)
    print("CHECKING DATA CONTENT DIFFERENCES")
    print("="*80)
    
    # Check GroupA SUB1
    print("\n[GroupA - SUB1]")
    
    sessions = ['Pre1', 'Post1', 'Pre2', 'Post2']
    data_samples = {}
    
    for session in sessions:
        file_path = root_dir / 'GroupA' / session / 'SUB1Adjustment1_cleaned.set'
        if not file_path.exists():
            print(f"  {session}: File not found")
            continue
        
        try:
            raw = loader.load_set_file(file_path, resample_rate=256)
            data = raw.get_data()
            
            # Get a sample of data (first 1000 samples, first 10 channels)
            sample = data[:10, :1000]
            data_samples[session] = sample
            
            print(f"  {session}:")
            print(f"    Mean: {np.mean(data):.6e}")
            print(f"    Std: {np.std(data):.6e}")
            print(f"    Range: [{np.min(data):.6e}, {np.max(data):.6e}]")
            
        except Exception as e:
            print(f"  {session}: Error loading - {str(e)}")
    
    # Compare Pre1 vs Post1
    if 'Pre1' in data_samples and 'Post1' in data_samples:
        diff = np.abs(data_samples['Pre1'] - data_samples['Post1'])
        print(f"\n  Pre1 vs Post1 difference:")
        print(f"    Max difference: {np.max(diff):.6e}")
        print(f"    Mean difference: {np.mean(diff):.6e}")
        
        if np.max(diff) < 1e-10:
            print(f"    🔴 WARNING: Files appear IDENTICAL (diff < 1e-10)")
        else:
            print(f"    ✓ Files are different")
    
    # Compare Pre2 vs Post2
    if 'Pre2' in data_samples and 'Post2' in data_samples:
        diff = np.abs(data_samples['Pre2'] - data_samples['Post2'])
        print(f"\n  Pre2 vs Post2 difference:")
        print(f"    Max difference: {np.max(diff):.6e}")
        print(f"    Mean difference: {np.mean(diff):.6e}")
        
        if np.max(diff) < 1e-10:
            print(f"    🔴 WARNING: Files appear IDENTICAL (diff < 1e-10)")
        else:
            print(f"    ✓ Files are different")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    check_duplicate_files()
    check_data_content_differences()
    print("\n✓ DIAGNOSTIC COMPLETE")
