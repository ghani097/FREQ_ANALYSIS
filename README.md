# EEG Frequency Analysis Tool

A PyQt6 desktop application for comparing EEG frequency-band power between sessions (e.g., pre- vs post-intervention) with cluster-based permutation testing and publication-quality output. Built on MNE-Python.

## What It Does

Point the tool at a folder of EEGLAB `.set/.fdt` files organised by group and session. It will:

1. **Load & align channels** across subjects (handles variable channel counts from bad-channel rejection)
2. **Compute PSD** via Welch's method for each standard frequency band
3. **Run statistics** -- cluster-based permutation tests (n >= 5) or paired/independent t-tests with FDR correction
4. **Generate figures** -- per-band topoplots, summary bar charts, statistics tables (300 DPI PNG)
5. **Write a methods section** -- ready-to-paste text describing the analysis for a manuscript

## Features

- **5 frequency bands** -- Delta (1-4 Hz), Theta (4-8 Hz), Alpha (8-13 Hz), Beta (13-30 Hz), Gamma (30-45 Hz)
- **Flexible session pairing** -- select any sessions as baseline or comparison; cartesian product pairing (M baselines x N comparisons)
- **Auto-detection fallback** -- sessions with "pre" in the name default to baseline, "post" to comparison
- **Adaptive statistics** -- automatically falls back from cluster permutation to t-test when sample size is small
- **Smart channel alignment** -- finds common channels across subjects, progressively excludes worst-case subjects if needed
- **Handles epoched data** -- reads EEGLAB epoched `.set` files and concatenates into continuous data, or averages PSD per epoch
- **Publication outputs** -- topoplots with significance markers, summary bar charts, statistics tables, auto-generated methods and results sections
- **GUI controls** -- configure resampling, epoch length, frequency range, permutations, alpha levels, test type, and FDR correction
- **Headless runner** -- scriptable CLI via `run_freq.py` for automated pipelines
- **Universal mode** -- optional `py_gui_universal.py` / `py_freq_universal.py` workflow for N groups and all ordered session-pair comparisons

## Requirements

- Python 3.10+
- Dependencies listed in `requirements_python.txt`

### Core dependencies

| Package | Purpose |
|---------|---------|
| MNE-Python | EEG data loading, PSD, cluster permutation tests, topoplots |
| NumPy / SciPy | Array operations, t-tests, FDR correction |
| Matplotlib | Publication figures |
| PyQt6 | GUI framework |

## Installation

```bash
pip install -r requirements_python.txt
```

On Windows you can also run `INSTALL_PYTHON.bat`, which checks for Python and installs all dependencies.

## Usage

```bash
python py_gui_main.py
```

### Scripted / headless usage

```bash
python run_freq.py --input E:\path\to\data --output E:\path\to\results
python run_freq.py --input E:\path\to\data --output E:\path\to\results --baseline-sessions pre --comparison-sessions post6W post12W post16W
python py_gui_universal.py
```

### Workflow

1. **Browse** to a root data directory and click **Scan Data**
2. **Assign session roles** -- select which sessions are baseline and which are comparison
3. **Adjust parameters** if needed (defaults work for most cases)
4. **Run Analysis** -- results and figures are saved to a `Results_Python/` folder and opened automatically

### Expected data layout

```
root_directory/
  Group1/
    SessionA/          # e.g., Pre, Baseline
      subject01.set
      subject02.set
    SessionB/          # e.g., Post6W, PostTx
      subject01.set
      subject02.set
  Group2/
    SessionA/
    SessionB/
```

Folders whose names start with `results` (case-insensitive) are automatically excluded from scanning.

## Project Structure

```
FREQ_ANALYSIS/
  py_gui_main.py           # PyQt6 GUI (main window, worker thread)
  py_analyzer.py            # Analysis engine (PSD, statistics, channel alignment)
  py_data_loader.py         # EEGLAB .set/.fdt loader and data validator
  py_visualizer.py          # Figure generation (topoplots, bar charts, tables, methods text)
  py_config.py              # Configuration constants (bands, defaults, plot settings)
  py_freq_universal.py      # Universal N-group / N-session analysis engine
  py_gui_universal.py       # Universal PyQt6 GUI
  run_freq.py               # Headless CLI runner
  diag_cluster_pvalues.py   # Diagnostic cluster-permutation helper
  py_diagnostic.py          # Diagnostic utilities
  show_all_markers.py       # Marker/event inspection utility
  requirements_python.txt   # Python dependencies
  INSTALL_PYTHON.bat        # Windows installer script
  docs/                     # Development notes
  tests/                    # Test scripts
```

## Configuration

Key parameters are configurable through the GUI or in `py_config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Resample Rate | Original | Keep native sampling rate, or resample to a target Hz |
| Epoch Length | 2.0 s | Window duration for PSD computation |
| Frequency Range | 1-45 Hz | Analysis band limits |
| Permutations | 1000 | Iterations for cluster permutation test |
| Cluster Alpha | 0.05 | Threshold for cluster formation |
| Significance Alpha | 0.05 | P-value threshold for significance |
| Min Neighbor Channels | 2 | Spatial constraint for cluster test |
| Test Type | Two-tailed | Two-tailed, or one-tailed (positive/negative) |
| Statistical Method | Auto | Auto, cluster permutation, paired t-test, or independent t-test |
| FDR Correction | On | Benjamini-Hochberg correction for multiple comparisons |

## Output

Each analysis run creates a timestamped results folder containing:

- **Per-band topoplots** -- 3-panel figures (group A change, group B change, between-group difference) with significance markers
- **Summary bar chart** -- all bands side-by-side with error bars and significance stars
- **Statistics table** -- channel-level p-values, t-statistics, and effect sizes
- **Methods section** -- `.txt` file with a publication-ready description of the analysis pipeline
- **Results section** -- `.txt` and `.md` summaries of significant findings across all comparisons

## License

This project is provided as-is for research use.
