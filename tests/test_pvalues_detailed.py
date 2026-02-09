"""
Check RAW vs FDR-CORRECTED p-values
This will show if FDR is the problem
"""

import sys
from pathlib import Path
from py_config import DEFAULT_PARAMS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer

def test_p_values():
    """Test with alpha=0.5 and see actual p-values"""
    
    print("="*80)
    print("TESTING P-VALUES (Alpha = 0.5)")
    print("="*80)
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    scan_info = loader.scan_directory()
    
    # Configuration with HIGH alpha (0.5)
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\TEST_OUTPUT')),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'significance_alpha': 0.5,  # VERY LENIENT!
        'process_all_session_pairs': False,  # Just first pair
        **{k: v for k, v in DEFAULT_PARAMS.items() if k != 'significance_alpha'}
    }
    
    Path(config['output_dir']).mkdir(exist_ok=True, parents=True)
    
    print(f"\n[CONFIG]")
    print(f"  Significance Alpha: {config['significance_alpha']}")
    print(f"  Statistical Method: {config['statistical_method']}")
    
    def progress_callback(msg):
        try:
            print(f"[PROGRESS] {msg}")
        except:
            pass
    
    try:
        print("\n" + "="*80)
        print("RUNNING ANALYSIS")
        print("="*80)
        
        analyzer = FrequencyAnalyzer(config, progress_callback)
        results = analyzer.run_analysis()
        
        print("\n" + "="*80)
        print("DETAILED P-VALUE ANALYSIS")
        print("="*80)
        
        # Check Alpha band as example
        if 'Alpha' in results:
            alpha_result = results['Alpha']
            stat_result = alpha_result.get('stat_result', {})
            
            print(f"\n[Alpha Band Results]")
            print(f"  Statistical method: {stat_result.get('method', 'N/A')}")
            
            # Get raw and corrected p-values
            if 'p_uncorrected' in stat_result:
                p_raw = stat_result['p_uncorrected']
                p_fdr = stat_result['p_corrected']
                
                import numpy as np
                
                print(f"\nRAW P-VALUES (before FDR):")
                print(f"  Min: {np.min(p_raw):.6f}")
                print(f"  Max: {np.max(p_raw):.6f}")
                print(f"  Mean: {np.mean(p_raw):.6f}")
                print(f"  Channels with p < 0.05: {np.sum(p_raw < 0.05)}")
                print(f"  Channels with p < 0.5: {np.sum(p_raw < 0.5)}")
                
                print(f"\nFDR-CORRECTED P-VALUES:")
                print(f"  Min: {np.min(p_fdr):.6f}")
                print(f"  Max: {np.max(p_fdr):.6f}")
                print(f"  Mean: {np.mean(p_fdr):.6f}")
                print(f"  Channels with p < 0.05: {np.sum(p_fdr < 0.05)}")
                print(f"  Channels with p < 0.5: {np.sum(p_fdr < 0.5)}")
                
                # Show first 10 channels
                print(f"\nFirst 10 channels detail:")
                for i in range(min(10, len(p_raw))):
                    print(f"  Ch{i}: raw={p_raw[i]:.4f}, FDR={p_fdr[i]:.4f}")
                    if p_raw[i] < 0.5:
                        print(f"        -> RAW would be sig at 0.5!")
                    if p_fdr[i] < 0.5:
                        print(f"        -> FDR would be sig at 0.5!")
            
            # Check how many significant
            sig_channels = alpha_result.get('sig_channels', [])
            print(f"\n  Significant channels found: {len(sig_channels)}")
            
            if len(sig_channels) == 0:
                print(f"\n  🔴 NO SIGNIFICANT CHANNELS even at alpha=0.5!")
                print(f"  This means ALL FDR-corrected p-values are > 0.5")
        
        print("\n" + "="*80)
        return True
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_p_values()
    sys.exit(0 if success else 1)
