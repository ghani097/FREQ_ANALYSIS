"""
Quick test to generate a figure with the new settings
- No p-values shown
- Just markers for significance
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
    
    output_dir = Path(r'TEST_NO_PVALUES')
    output_dir.mkdir(exist_ok=True, parents=True)
    
    config = {
        'root_dir': str(root_dir),
        'output_dir': str(output_dir),
        'sessions': scan_info['sessions'],
        'statistical_method': 'independent_ttest',
        'significance_alpha': 0.05,
        'skip_fdr_correction': True,  # To get some significance
        'process_all_session_pairs': False,
        **{k: v for k, v in DEFAULT_PARAMS.items() if k not in ['significance_alpha']}
    }
    
    print("="*80)
    print("TESTING: Plots without p-values")
    print("="*80)
    print(f"\nOutput: {output_dir}")
    print("Generating figures...")
    
    # Run analysis (silent)
    analyzer = FrequencyAnalyzer(config, lambda x: None)
    results = analyzer.run_analysis()
    
    # Create visualizations
    visualizer = ResultVisualizer(output_dir)
    
    # Generate Beta band (has significance)
    if 'Beta' in results:
        print("\nCreating Beta band plot...")
        fig_path = visualizer.plot_band_result(results['Beta'], show=False)
        print(f"✓ Saved: {fig_path}")
        
        stats = results['Beta']['statistics']
        if 'p_uncorrected' in stats:
            p_raw = stats['p_uncorrected']
            n_sig = np.sum(p_raw < 0.05)
            print(f"  Significant channels: {n_sig}")
            print(f"  Min p-value: {np.min(p_raw):.4f}")
    
    # Generate summary
    print("\nCreating summary plot...")
    summary_path = visualizer.plot_summary(results, show=False)
    print(f"✓ Saved: {summary_path}")
    
    print("\n" + "="*80)
    print("CHECK THE FIGURES:")
    print("="*80)
    print(f"1. Open: {output_dir / 'figures'}")
    print(f"2. Look at the plots")
    print(f"3. You should see:")
    print(f"   ✓ RED STAR markers on significant channels")
    print(f"   ✓ NO p-values in titles or labels")
    print(f"   ✓ NO significance stars (*, **, ***)")
    print("="*80)

if __name__ == '__main__':
    test()
