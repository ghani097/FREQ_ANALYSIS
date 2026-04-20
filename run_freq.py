"""
run_freq.py
Headless CLI runner for FREQ_ANALYSIS.
Called by ResearchBuddy pipeline runner via:
    python run_freq.py --input <root_dir> --output <out_dir> [--p-value 0.05] [--stat-test auto]
Prints FREQ_COMPLETE on success.
"""

import argparse
import sys
import traceback
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend — must come before other matplotlib imports

from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer
from py_visualizer import ResultVisualizer




def _progress(msg: str) -> None:
    print(msg, flush=True)


def _safe_plot(label: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        _progress(f"  [FAIL] {label}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless FREQ_ANALYSIS runner")
    parser.add_argument("--input",   required=True, help="Root directory with EEG data")
    parser.add_argument("--output",  required=True, help="Output directory for results")

    # Statistical parameters
    parser.add_argument("--p-value",        type=float, default=0.05,
                        help="Significance alpha (default: 0.05)")
    parser.add_argument("--stat-method",    default="auto",
                        choices=["auto", "cluster", "paired_ttest", "independent_ttest"],
                        help="Statistical method (default: auto)")
    parser.add_argument("--cluster-alpha",  type=float, default=0.05,
                        help="Cluster formation threshold (default: 0.05)")
    parser.add_argument("--tail",           type=int,   default=0,
                        choices=[-1, 0, 1],
                        help="Test tail: 0=two-tailed, 1=pos, -1=neg (default: 0)")
    parser.add_argument("--min-neighbor-chan", type=int, default=2,
                        help="Min adjacent channels for cluster (default: 2)")
    parser.add_argument("--skip-fdr",       action="store_true", default=False,
                        help="Skip FDR correction (use raw p-values)")
    parser.add_argument("--n-permutations", type=int, default=1000,
                        help="Permutation test iterations (default: 1000)")

    # Signal / epoch parameters
    parser.add_argument("--epoch-length",   type=float, default=2.0,
                        help="Epoch length in seconds for Welch PSD (default: 2.0)")
    parser.add_argument("--freq-min",       type=int,   default=1,
                        help="Low frequency bound Hz (default: 1)")
    parser.add_argument("--freq-max",       type=int,   default=45,
                        help="High frequency bound Hz (default: 45)")
    parser.add_argument("--ignore-epochs",  dest="ignore_epochs", action="store_true")
    parser.add_argument("--no-ignore-epochs", dest="ignore_epochs", action="store_false",
                        help="Compute PSD per epoch then average (default: treat as continuous)")
    parser.set_defaults(ignore_epochs=True)

    # Plot options
    parser.add_argument("--individual-plots",    dest="individual_plots", action="store_true")
    parser.add_argument("--no-individual-plots", dest="individual_plots", action="store_false",
                        help="Skip per-band topoplots (faster)")
    parser.set_defaults(individual_plots=True)

    # Session role overrides (auto-detected from folder names by default)
    parser.add_argument("--baseline-sessions",   nargs="*", default=[],
                        help="Baseline session names (auto-detected if omitted)")
    parser.add_argument("--comparison-sessions", nargs="*", default=[],
                        help="Comparison session names (auto-detected if omitted)")
    args = parser.parse_args()

    root_dir   = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Scan directory to discover groups/sessions.
    # Always exclude the output dir (which may live inside root_dir) and any
    # directory whose name starts with 'results' (already excluded by loader).
    loader = EEGDataLoader(root_dir)
    exclude = [output_dir.name] if output_dir.name else []
    try:
        scan_info = loader.scan_directory(exclude_dirs=exclude)
    except ValueError as exc:
        _progress(f"FATAL: {exc}")
        _progress(
            "\nExpected folder structure under --input:\n"
            "  <input>/\n"
            "    GroupA/\n"
            "      pre/   ← session folder with *.set files\n"
            "      post/\n"
            "    GroupB/\n"
            "      pre/\n"
            "      post/\n"
            "\nMake sure --input points to the folder that CONTAINS group folders,\n"
            "not to a group folder itself."
        )
        sys.exit(1)

    sessions = scan_info.get("sessions", [])

    # Auto-detect baseline / comparison sessions from names when not supplied.
    if not args.baseline_sessions:
        baseline_sessions = [s for s in sessions if "pre" in s.lower()]
        if not baseline_sessions:
            baseline_sessions = sessions[:1]
    else:
        baseline_sessions = args.baseline_sessions

    if not args.comparison_sessions:
        comparison_sessions = [s for s in sessions if "post" in s.lower()]
        if not comparison_sessions:
            comparison_sessions = sessions[1:] if len(sessions) > 1 else sessions
    else:
        comparison_sessions = args.comparison_sessions

    _progress(f"Groups found: {scan_info.get('groups', [])}")
    _progress(f"Sessions found: {sessions}")
    _progress(f"Baseline sessions: {baseline_sessions}")
    _progress(f"Comparison sessions: {comparison_sessions}")

    config = {
        "root_dir":                  str(root_dir),
        "output_dir":                str(output_dir),
        "sessions":                  sessions,
        "baseline_sessions":         baseline_sessions,
        "comparison_sessions":       comparison_sessions,
        "significance_alpha":        args.p_value,
        "cluster_alpha":             args.cluster_alpha,
        "n_permutations":            args.n_permutations,
        "epoch_length":              args.epoch_length,
        "freq_range":                (args.freq_min, args.freq_max),
        "min_neighbor_chan":         args.min_neighbor_chan,
        "tail":                      args.tail,
        "n_jobs":                    -1,
        "statistical_method":        args.stat_method,
        "process_all_session_pairs": True,
        "skip_fdr_correction":       args.skip_fdr,
        "generate_individual_plots": args.individual_plots,
        "resample_rate":             None,
        "ignore_epochs":             args.ignore_epochs,
    }

    try:
        analyzer = FrequencyAnalyzer(config, _progress)
        results  = analyzer.run_analysis()

        if analyzer.detected_sfreq:
            config["detected_sfreq"] = analyzer.detected_sfreq

        visualizer = ResultVisualizer(output_dir)
        _progress("\n=== Creating figures ===")

        if results and isinstance(results, dict):
            first_val = list(results.values())[0] if results else {}
            is_single = isinstance(first_val, dict) and "band_name" in first_val

            if is_single:
                comparison_name = None
                fv = list(results.values())[0]
                if "pre_session" in fv and "post_session" in fv:
                    comparison_name = f"{fv['post_session']}_vs_{fv['pre_session']}"

                for band_name, result in results.items():
                    _safe_plot(f"{band_name} topoplot",
                               lambda r=result: visualizer.plot_band_result(r, show=False))
                _safe_plot("summary",
                           lambda: visualizer.plot_summary(results, show=False, comparison_name=comparison_name))
                sig_alpha = config["significance_alpha"]
                _safe_plot("statistics table",
                           lambda sa=sig_alpha: visualizer.plot_statistics_table(
                               results, comparison_name=comparison_name, sig_alpha=sa))
                try:
                    visualizer.generate_methods_section(results, comparison_name=comparison_name, config=config)
                except Exception as exc:
                    _progress(f"  [FAIL] methods section: {exc}")

            else:
                # Multiple session-pair comparisons
                for comparison_name, band_results in results.items():
                    if comparison_name.startswith("_") or not band_results:
                        continue
                    _progress(f"\n  === {comparison_name} ===")

                    for band_name, result in band_results.items():
                        result["comparison_name"] = comparison_name
                        _safe_plot(f"{comparison_name}/{band_name}",
                                   lambda r=result: visualizer.plot_band_result(r, show=False))
                    _safe_plot(f"{comparison_name} summary",
                               lambda cn=comparison_name, br=band_results:
                               visualizer.plot_summary(br, show=False, comparison_name=cn))
                    sig_alpha = config["significance_alpha"]
                    _safe_plot(f"{comparison_name} table",
                               lambda cn=comparison_name, br=band_results, sa=sig_alpha:
                               visualizer.plot_statistics_table(br, comparison_name=cn, sig_alpha=sa))
                    try:
                        visualizer.generate_methods_section(band_results, comparison_name=comparison_name, config=config)
                    except Exception as exc:
                        _progress(f"  [FAIL] {comparison_name} methods: {exc}")

                _progress("\n=== Generating Publication-Ready Results Section ===")
                try:
                    visualizer.generate_results_section(results, config=config)
                except Exception as exc:
                    _progress(f"  [FAIL] results section: {exc}")

        _progress(f"\nResults saved to: {output_dir}")
        print("FREQ_COMPLETE", flush=True)

    except Exception as exc:
        _progress(f"FATAL: {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
