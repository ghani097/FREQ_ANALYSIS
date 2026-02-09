"""
Test both fixes:
1. Summary plot shows comparison name (Post1_vs_Pre1 or Post2_vs_Pre2)
2. Markers changed from star to X
"""

import sys
from pathlib import Path
from py_config import DEFAULT_PARAMS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer
from py_visualizer import ResultVisualizer
import numpy as np

def test():
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    scan_info = loader.scan_directory()
    
    output_dir = Path(r'TEST_FINAL_FIXES')
    output_dir.mkdir(exist_ok=True, parents=True)
    
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(output_dir),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'significance_alpha': 0.05,
        'skip_fdr_correction': True,  # To get significance
        'process_all_session_pairs': True,  # Test both comparisons
        **{k: v for k, v in DEFAULT_PARAMS.items() if k not in ['significance_alpha']}
    }
    
    print("="*80)
    print("TESTING FINAL FIXES")
    print("="*80)
    print(f"\n1. Multi-session pairs: {config['process_all_session_pairs']}")
    print(f"2. Marker changed: star to X")
    print(f"\nOutput: {output_dir}")
    
    # Run analysis (silent)
    print("\nRunning analysis...")
    analyzer = FrequencyAnalyzer(config, lambda x: None)
    results = analyzer.run_analysis()
    
    # Create visualizations
    visualizer = ResultVisualizer(output_dir)
    
    print("\nCreating figures...")
    
    # Process results (should be multi-comparison)
    if isinstance(list(results.values())[0], dict) and 'band_name' not in list(results.values())[0]:
        # Multiple comparisons
        print(f"\nFOUND {len(results)} comparisons:")
        for comparison_name in results.keys():
            print(f"  - {comparison_name}")
            
        # Create summaries for each
        for comparison_name, band_results in results.items():
            print(f"\nCreating summary for: {comparison_name}")
            summary_path = visualizer.plot_summary(band_results, show=False, comparison_name=comparison_name)
            print(f"  SAVED: {Path(summary_path).name}")
    else:
        print("ERROR: Expected multiple comparisons but got single")
    
    print("\n" + "="*80)
    print("CHECK THE RESULTS:")
    print("="*80)
    print(f"\n1. Open: {output_dir / 'figures'}")
    print(f"\n2. You should see TWO summary plots:")
    print(f"   - Post1_vs_Pre1_summary.png")
    print(f"   - Post2_vs_Pre2_summary.png")
    print(f"   - Each has comparison name in title")
    print(f"\n3. Markers should be 'X' shapes (not 5-pointed stars)")
    print(f"\n4. No p-values shown in plots")
    print("="*80)

if __name__ == '__main__':
    test()
