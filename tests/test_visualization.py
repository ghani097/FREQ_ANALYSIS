"""
Test script to verify visualization features work correctly.
Tests: statistics table generation, individual plots toggle.
"""

import sys
import os
import numpy as np
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from py_analyzer import FrequencyAnalyzer
from py_visualizer import ResultVisualizer
from py_config import FREQUENCY_BANDS


def safe_print(msg):
    """Print with Unicode error handling."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode('ascii', 'replace').decode('ascii')
        print(safe_msg)


def test_visualization():
    """Test visualization features including statistics table."""

    print("=" * 70)
    print("TEST: Visualization Features")
    print("=" * 70)

    # Configuration
    config = {
        'root_dir': r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD',
        'output_dir': r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\TEST_VIS_OUTPUT',
        'sessions': ['Pre1', 'Post1', 'Pre2', 'Post2'],
        'resample_rate': 256,
        'epoch_length': 2.0,
        'freq_range': (1, 45),
        'n_permutations': 100,
        'cluster_alpha': 0.05,
        'significance_alpha': 0.05,
        'min_neighbor_chan': 0,
        'tail': 0,
        'n_jobs': -1,
        'statistical_method': 'independent_ttest',
        'process_all_session_pairs': True,
        'skip_fdr_correction': True
    }

    # Create output directory
    output_dir = Path(config['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run analysis
    print("\n1. Running analysis...")
    analyzer = FrequencyAnalyzer(config, safe_print)
    results = analyzer.run_analysis()

    # Create visualizer
    print("\n2. Testing visualizations...")
    visualizer = ResultVisualizer(output_dir)

    # Test statistics table for each comparison
    comparison_names = list(results.keys())
    print(f"   Found {len(comparison_names)} comparisons")

    for comp_name in comparison_names:
        band_results = results[comp_name]
        print(f"\n   Testing {comp_name}:")

        # Test statistics table
        print(f"     - Creating statistics table...")
        table_path = visualizer.plot_statistics_table(band_results, comparison_name=comp_name)
        if table_path and Path(table_path).exists():
            print(f"       [OK] Table created: {Path(table_path).name}")

            # Check CSV was also created
            csv_path = table_path.replace('.png', '.csv')
            if Path(csv_path).exists():
                print(f"       [OK] CSV created: {Path(csv_path).name}")
            else:
                print(f"       [WARN] CSV not found")
        else:
            print(f"       [FAIL] Table creation failed")

        # Test summary plot
        print(f"     - Creating summary plot...")
        summary_path = visualizer.plot_summary(band_results, show=False, comparison_name=comp_name)
        if summary_path and Path(summary_path).exists():
            print(f"       [OK] Summary created: {Path(summary_path).name}")
        else:
            print(f"       [FAIL] Summary creation failed")

        # Test one individual band plot
        first_band = list(band_results.keys())[0]
        result = band_results[first_band]
        result['comparison_name'] = comp_name
        print(f"     - Creating individual {first_band} plot...")
        band_path = visualizer.plot_band_result(result, show=False)
        if band_path and Path(band_path).exists():
            print(f"       [OK] Band plot created: {Path(band_path).name}")
        else:
            print(f"       [FAIL] Band plot creation failed")

        # Test methods section generation
        print(f"     - Generating methods section...")
        methods_path = visualizer.generate_methods_section(band_results, comparison_name=comp_name, config=config)
        if methods_path and Path(methods_path).exists():
            print(f"       [OK] Methods section created: {Path(methods_path).name}")
        else:
            print(f"       [FAIL] Methods section creation failed")

    # Generate complete results section
    print("\n3. Generating publication-ready results section...")
    results_path = visualizer.generate_results_section(results, config=config)
    if results_path and Path(results_path).exists():
        print(f"   [OK] Results section created: {Path(results_path).name}")
        md_path = results_path.replace('.txt', '.md')
        if Path(md_path).exists():
            print(f"   [OK] Markdown version created: {Path(md_path).name}")
    else:
        print(f"   [FAIL] Results section creation failed")

    # List all created files
    print("\n" + "=" * 70)
    print("CREATED FILES:")
    print("=" * 70)
    figures_dir = output_dir / 'figures'
    if figures_dir.exists():
        for f in sorted(figures_dir.glob('*')):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.1f} KB)")
    else:
        print("  No figures directory found!")

    print("\n" + "=" * 70)
    print("[SUCCESS] Visualization test complete!")
    print(f"Check output in: {output_dir}")
    print("=" * 70)

    return True


if __name__ == '__main__':
    success = test_visualization()
    sys.exit(0 if success else 1)
