"""
DIRECT P-VALUE CHECK - Show actual numbers
"""

import sys
from pathlib import Path
from py_config import DEFAULT_PARAMS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer
import numpy as np

def test():
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    scan_info = loader.scan_directory()
    
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(Path(r'TEST_OUT')),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'significance_alpha': 0.5,  # HIGH!
        'process_all_session_pairs': False,
        **{k: v for k, v in DEFAULT_PARAMS.items() if k != 'significance_alpha'}
    }
    
    Path(config['output_dir']).mkdir(exist_ok=True, parents=True)
    
    print("Running with alpha=0.5...")
    
    analyzer = FrequencyAnalyzer(config, lambda x: None)  # Silent
    results = analyzer.run_analysis()
    
    print("\n" + "="*80)
    print("P-VALUE ANALYSIS - Alpha Band")
    print("="*80)
    
    if 'Alpha' in results:
        result = results['Alpha']
        stats = result.get('statistics', {})
        
        if 'p_uncorrected' in stats:
            p_raw = stats['p_uncorrected']
            p_fdr = stats['p_corrected']
            
            print(f"\nRAW P-VALUES:")
            print(f"  Min: {np.min(p_raw):.6f}")
            print(f"  Max: {np.max(p_raw):.6f}")
            print(f"  # < 0.05: {np.sum(p_raw < 0.05)}/{len(p_raw)}")
            print(f"  # < 0.50: {np.sum(p_raw < 0.50)}/{len(p_raw)}")
            
            print(f"\nFDR-CORRECTED P-VALUES:")
            print(f"  Min: {np.min(p_fdr):.6f}")
            print(f"  Max: {np.max(p_fdr):.6f}")
            print(f"  # < 0.05: {np.sum(p_fdr < 0.05)}/{len(p_fdr)}")
            print(f"  # < 0.50: {np.sum(p_fdr < 0.50)}/{len(p_fdr)}")
            
            if np.min(p_raw) < 0.50 and np.min(p_fdr) >= 0.50:
                print(f"\nPROBLEM FOUND:")
                print(f"  Some RAW p-values < 0.50")
                print(f"  But ALL FDR p-values >= 0.50")
                print(f"  FDR correction is too aggressive for this small sample!")
        else:
            print("No p-values found in statistics")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    test()
