"""
Test the new multi-session pair analysis feature
"""

import sys
from pathlib import Path
from py_config import DEFAULT_PARAMS, FREQUENCY_BANDS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer

def test_multi_session_pairs():
    """Test analyzing both Pre1/Post1 AND Pre2/Post2"""
    
    print("="*80)
    print("TESTING: MULTI-SESSION PAIR ANALYSIS")
    print("="*80)
    
    # Setup
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    scan_info = loader.scan_directory()
    
    print(f"\n[DATA SCAN]")
    print(f"  Found {scan_info['total_files']} .set files")
    print(f"  Groups: {', '.join(scan_info['groups'])}")
    print(f"  Sessions: {', '.join(scan_info['sessions'])}")
    
    # Configuration with ALL pairs enabled
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\TEST_OUTPUT_MULTI')),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'process_all_session_pairs': True,  # NEW FEATURE!
        **DEFAULT_PARAMS
    }
    
    Path(config['output_dir']).mkdir(exist_ok=True, parents=True)
    
    print(f"\n[CONFIG]")
    print(f"  Process all session pairs: {config['process_all_session_pairs']}")
    print(f"  Statistical Method: {config['statistical_method']}")
    print(f"  Output: {config['output_dir']}")
    
    def progress_callback(msg):
        # Avoid unicode issues
        try:
            print(f"[PROGRESS] {msg}")
        except:
            print(f"[PROGRESS] {msg.encode('ascii', 'ignore').decode()}")
    
    try:
        print("\n" + "="*80)
        print("RUNNING ANALYSIS")
        print("="*80)
        
        analyzer = FrequencyAnalyzer(config, progress_callback)
        results = analyzer.run_analysis()
        
        print("\n" + "="*80)
        print("RESULTS SUMMARY")
        print("="*80)
        
        # Check structure
        if not isinstance(results, dict):
            print("ERROR: Results is not a dict")
            return False
        
        # Check if we have multiple comparisons
        first_key = list(results.keys())[0]
        first_val = results[first_key]
        
        if isinstance(first_val, dict) and 'band_name' not in first_val:
            # Multiple comparisons
            print(f"\nFound {len(results)} session pair comparisons:")
            for comparison_name, band_results in results.items():
                print(f"\n[{comparison_name}]")
                print(f"  Bands analyzed: {len(band_results)}")
                
                for band_name, result in band_results.items():
                    stat_result = result.get('stat_result', {})
                    method = stat_result.get('method', 'N/A')
                    n_sig = len(result.get('sig_channels', []))
                    print(f"    {band_name}: method={method}, sig_channels={n_sig}")
        else:
            # Single comparison (backward compatible)
            print(f"\nSingle comparison (backward compatible mode)")
            print(f"  Bands analyzed: {len(results)}")
            
            for band_name, result in results.items():
                stat_result = result.get('stat_result', {})
                method = stat_result.get('method', 'N/A')
                n_sig = len(result.get('sig_channels', []))
                print(f"    {band_name}: method={method}, sig_channels={n_sig}")
        
        print("\n" + "="*80)
        print("TEST COMPLETED SUCCESSFULLY")
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
    success = test_multi_session_pairs()
    sys.exit(0 if success else 1)
