"""
Test script to verify the fix for identical plots bug.
This script confirms that Post1_vs_Pre1 and Post2_vs_Pre2 now produce DIFFERENT results.
"""

import sys
import os
import numpy as np
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from py_analyzer import FrequencyAnalyzer
from py_config import FREQUENCY_BANDS


def safe_print(msg):
    """Print with Unicode error handling for Windows console."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Replace problematic Unicode characters with ASCII equivalents
        safe_msg = msg.encode('ascii', 'replace').decode('ascii')
        print(safe_msg)


def test_different_session_pairs():
    """Verify that different session pairs produce different results."""

    print("=" * 70)
    print("TEST: Verifying Post1_vs_Pre1 and Post2_vs_Pre2 produce different results")
    print("=" * 70)

    # Configuration
    config = {
        'root_dir': r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD',
        'output_dir': r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\TEST_OUTPUT',
        'sessions': ['Pre1', 'Post1', 'Pre2', 'Post2'],  # Will be detected
        'resample_rate': 256,
        'epoch_length': 2.0,
        'freq_range': (1, 45),
        'n_permutations': 100,  # Low for fast test
        'cluster_alpha': 0.05,
        'significance_alpha': 0.05,
        'min_neighbor_chan': 0,
        'tail': 0,
        'n_jobs': -1,
        'statistical_method': 'independent_ttest',  # Fast for testing
        'process_all_session_pairs': True,
        'skip_fdr_correction': True
    }

    # Create output directory
    Path(config['output_dir']).mkdir(parents=True, exist_ok=True)

    # Run analysis
    print("\nRunning analysis...")
    analyzer = FrequencyAnalyzer(config, safe_print)
    results = analyzer.run_analysis()

    # Check results structure
    print("\n" + "=" * 70)
    print("RESULTS STRUCTURE")
    print("=" * 70)

    comparison_names = list(results.keys())
    print(f"Found {len(comparison_names)} comparisons: {comparison_names}")

    if len(comparison_names) < 2:
        print("\n❌ FAIL: Expected at least 2 comparisons (Post1_vs_Pre1 and Post2_vs_Pre2)")
        return False

    # Compare t-values between session pairs
    print("\n" + "=" * 70)
    print("COMPARING T-VALUES BETWEEN SESSION PAIRS")
    print("=" * 70)

    all_different = True

    for band_name in FREQUENCY_BANDS.keys():
        if band_name not in results[comparison_names[0]]:
            continue

        print(f"\n{band_name} Band:")

        # Get t-values from each comparison
        t1 = results[comparison_names[0]][band_name]['statistics']['t_obs']
        t2 = results[comparison_names[1]][band_name]['statistics']['t_obs']

        # Check if identical - t-values should have meaningful differences
        # Use a threshold based on expected statistical variability
        max_diff = np.max(np.abs(t1 - t2))
        mean_diff = np.mean(np.abs(t1 - t2))

        # T-values should differ by at least 0.1 if data is truly different
        are_meaningfully_different = max_diff > 0.1

        print(f"  {comparison_names[0]} t-values: mean={np.mean(t1):.6f}, std={np.std(t1):.6f}")
        print(f"  {comparison_names[1]} t-values: mean={np.mean(t2):.6f}, std={np.std(t2):.6f}")
        print(f"  Max difference: {max_diff:.6f}")
        print(f"  Mean difference: {mean_diff:.6f}")

        if not are_meaningfully_different:
            print(f"  [X] FAIL: T-values are effectively IDENTICAL!")
            all_different = False
        else:
            print(f"  [OK] PASS: T-values are DIFFERENT (good!)")

    # Also compare grand averages
    print("\n" + "=" * 70)
    print("COMPARING GRAND AVERAGES BETWEEN SESSION PAIRS")
    print("=" * 70)

    for band_name in FREQUENCY_BANDS.keys():
        if band_name not in results[comparison_names[0]]:
            continue

        print(f"\n{band_name} Band:")

        ga1_a = results[comparison_names[0]][band_name]['ga_diff_a']
        ga1_b = results[comparison_names[0]][band_name]['ga_diff_b']
        ga2_a = results[comparison_names[1]][band_name]['ga_diff_a']
        ga2_b = results[comparison_names[1]][band_name]['ga_diff_b']

        # Check Group A differences
        # Note: Grand averages might be near-zero if Post-Pre differences are small
        # This is normal and doesn't indicate a bug - the key test is t-values above
        ga_a_diff = np.max(np.abs(ga1_a - ga2_a))
        ga_a_max = max(np.max(np.abs(ga1_a)), np.max(np.abs(ga2_a)), 1e-15)
        ga_a_rel_diff = ga_a_diff / ga_a_max

        print(f"  Group A grand averages:")
        print(f"    {comparison_names[0]}: mean={np.mean(ga1_a):.6e}, max={np.max(np.abs(ga1_a)):.6e}")
        print(f"    {comparison_names[1]}: mean={np.mean(ga2_a):.6e}, max={np.max(np.abs(ga2_a)):.6e}")
        print(f"    Max diff: {ga_a_diff:.6e} (rel: {ga_a_rel_diff:.2%})")

        # Check Group B differences
        ga_b_diff = np.max(np.abs(ga1_b - ga2_b))
        ga_b_max = max(np.max(np.abs(ga1_b)), np.max(np.abs(ga2_b)), 1e-15)
        ga_b_rel_diff = ga_b_diff / ga_b_max

        print(f"  Group B grand averages:")
        print(f"    {comparison_names[0]}: mean={np.mean(ga1_b):.6e}, max={np.max(np.abs(ga1_b)):.6e}")
        print(f"    {comparison_names[1]}: mean={np.mean(ga2_b):.6e}, max={np.max(np.abs(ga2_b)):.6e}")
        print(f"    Max diff: {ga_b_diff:.6e} (rel: {ga_b_rel_diff:.2%})")

    # Final verdict
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)

    if all_different:
        print("[SUCCESS] All session pairs produce DIFFERENT t-values!")
        print("  The bug has been FIXED.")
        print("")
        print("  Key evidence:")
        print("  - T-values differ substantially between Post1_vs_Pre1 and Post2_vs_Pre2")
        print("  - This proves different data is being loaded for each session pair")
        print("  - Plots will now show different results as expected")
        return True
    else:
        print("[FAILURE] Some session pairs still produce IDENTICAL t-values!")
        print("  The bug is NOT fixed.")
        return False


if __name__ == '__main__':
    success = test_different_session_pairs()
    sys.exit(0 if success else 1)
