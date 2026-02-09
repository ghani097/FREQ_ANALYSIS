"""
Simple diagnostic: What subjects are actually being compared?
"""

import numpy as np
from pathlib import Path
from py_data_loader import EEGDataLoader

def check_subject_matching():
    """Check what subjects are being matched"""
    
    print("="*80)
    print("SUBJECT MATCHING DIAGNOSTIC")
    print("="*80)
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    
    # Scan first
    scan_info = loader.scan_directory()
    
    print(f"\n[Scan Results]")
    print(f"Groups: {scan_info['groups']}")
    print(f"Sessions: {scan_info['sessions']}")
    print(f"\nSubjects dictionary:")
    for key, subjects in scan_info['subjects'].items():
        print(f"  {key}: {len(subjects)} subjects")
        if subjects:
            print(f"    First: {subjects[0]}")
    
    # Try matching
    print(f"\n[Matching GroupA Pre1 vs Post1]")
    matched_a = loader.get_matched_subjects('GroupA', 'Pre1', 'Post1')
    print(f"Matched: {len(matched_a)} subjects")
    print(f"List: {matched_a}")
    
    print(f"\n[Matching GroupB Pre1 vs Post1]")
    matched_b = loader.get_matched_subjects('GroupB', 'Pre1', 'Post1')
    print(f"Matched: {len(matched_b)} subjects")
    print(f"List: {matched_b}")
    
    # Check what the analyzer sees
    print(f"\n[What files actually exist]")
    
    for group in ['GroupA', 'GroupB']:
        for session in ['Pre1', 'Post1']:
            dir_path = root_dir / group / session
            if dir_path.exists():
                files = list(dir_path.glob('*.set'))
                print(f"\n{group}/{session}:")
                for f in files[:3]:  # First 3
                    print(f"  {f.name}")
                    print(f"    Stem: {f.stem}")

if __name__ == '__main__':
    check_subject_matching()
