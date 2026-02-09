"""
Test with FDR DISABLED - should show significant results
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
        'output_dir': str(Path(r'TEST_OUT_NO_FDR')),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'significance_alpha': 0.05,  # Normal threshold
        'skip_fdr_correction': True,  # DISABLE FDR!
        'process_all_session_pairs': False,
        **{k: v for k, v in DEFAULT_PARAMS.items() if k not in ['significance_alpha']}
    }
    
    Path(config['output_dir']).mkdir(exist_ok=True, parents=True)
    
    print("="*80)
    print("TESTING WITHOUT FDR CORRECTION")
    print("="*80)
    print(f"\nAlpha threshold: {config['significance_alpha']}")
    print(f"Skip FDR: {config['skip_fdr_correction']}")
    
    # Silent progress
    def silent(msg):
        pass
    
    analyzer = FrequencyAnalyzer(config, silent)
    results = analyzer.run_analysis()
    
    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)
    
    for band_name, result in results.items():
        stats = result.get('statistics', {})
        
        if 'p_uncorrected' in stats:
            p_raw = stats['p_uncorrected']
            p_used = stats['p_corrected']  # Should be same as raw if FDR skipped
            
            n_sig = np.sum(p_used < config['significance_alpha'])
            
            print(f"\n[{band_name}]")
            print(f"  Min p-value: {np.min(p_used):.6f}")
            print(f"  Significant channels: {n_sig}/{len(p_used)}")
            
            if n_sig > 0:
                print(f"  SUCCESS - Found significance!")
            else:
                print(f"  No significance (even without FDR)")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    test()
