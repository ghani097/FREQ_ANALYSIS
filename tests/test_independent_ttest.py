"""
Test script for Independent T-test + FDR functionality
Tests the new statistical method with small sample size (n=2 in GroupB)
"""

import sys
from pathlib import Path
from py_config import DEFAULT_PARAMS, FREQUENCY_BANDS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer

def test_independent_ttest():
    """Test Independent T-test with LIFE_Data_UPD"""
    
    print("="*80)
    print("TESTING: Independent T-test + FDR")
    print("="*80)
    
    # First, scan the data directory to get sessions
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    scan_info = loader.scan_directory()
    
    print(f"\n[DATA SCAN]")
    print(f"  Found {scan_info['total_files']} .set files")
    print(f"  Groups: {', '.join(scan_info['groups'])}")
    print(f"  Sessions: {', '.join(scan_info['sessions'])}")
    
    # Configuration matching GUI structure
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\TEST_OUTPUT')),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',  # Testing new feature
        **DEFAULT_PARAMS
    }
    
    # Create output directory
    Path(config['output_dir']).mkdir(exist_ok=True, parents=True)
    
    print(f"\n[CONFIG]")
    print(f"  Data Root: {config['root_dir']}")
    print(f"  Sessions: {config['sessions']}")
    print(f"  Statistical Method: {config['statistical_method']}")
    print(f"  Output: {config['output_dir']}")
    
    # Progress callback
    def progress_callback(msg):
        print(f"[PROGRESS] {msg}")
    
    try:
        # Run analysis
        print("\n" + "="*80)
        print("RUNNING ANALYSIS")
        print("="*80)
        
        analyzer = FrequencyAnalyzer(config, progress_callback)
        results = analyzer.run_analysis()
        
        print("\n" + "="*80)
        print("RESULTS SUMMARY")
        print("="*80)
        
        # Check results
        for band_name, result in results.items():
            print(f"\n[{band_name}]")
            print(f"  Frequency Range: {result.get('band_range', result.get('freq_range', 'N/A'))} Hz")
            print(f"  Statistical Method Used: {result.get('stat_result', {}).get('method', 'N/A')}")
            print(f"  Group A: {result.get('group_a', 'N/A')} (n={result.get('n_subjects_a', 'N/A')})")
            print(f"  Group B: {result.get('group_b', 'N/A')} (n={result.get('n_subjects_b', 'N/A')})")
            
            if 'sig_channels' in result and result['sig_channels']:
                print(f"  ✅ SIGNIFICANT CHANNELS FOUND: {len(result['sig_channels'])}")
                print(f"     Channels: {', '.join(result['sig_channels'][:10])}")  # First 10
            else:
                print(f"  ❌ NO SIGNIFICANT CHANNELS")
            
            # Show p-value info if available
            stat_result = result.get('stat_result', {})
            if 'p_corrected' in stat_result:
                p_corr = stat_result['p_corrected']
                min_p = min(p_corr)
                max_p = max(p_corr)
                print(f"     P-values (FDR): min={min_p:.6f}, max={max_p:.6f}")
        
        print("\n" + "="*80)
        print("TEST COMPLETED SUCCESSFULLY ✅")
        print("="*80)
        
        return True
        
    except Exception as e:
        print("\n" + "="*80)
        print(f"ERROR: {str(e)}")
        print("="*80)
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_independent_ttest()
    sys.exit(0 if success else 1)
