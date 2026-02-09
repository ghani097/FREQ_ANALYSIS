# EEG Frequency Analysis Tool

A Python-based GUI application for EEG frequency-band power analysis with statistical testing and publication-quality visualizations. Built on MNE-Python.

## Features

- **Frequency Band Analysis** - Delta (1-4 Hz), Theta (4-8 Hz), Alpha (8-13 Hz), Beta (13-30 Hz), Gamma (30-45 Hz)
- **Statistical Testing** - Cluster-based permutation tests, paired/independent t-tests, FDR correction
- **Multi-Session Support** - Automatic Pre/Post session pairing across multiple time points
- **Publication-Ready Figures** - Topoplots, summary bar charts, statistics tables (300 DPI)
- **PyQt6 GUI** - Point-and-click interface for configuring and running analyses
- **EEGLAB Compatible** - Reads `.set/.fdt` files directly

## Requirements

- Python 3.10+
- Dependencies listed in `requirements_python.txt`

## Installation

```bash
pip install -r requirements_python.txt
```

Or on Windows, run `INSTALL_PYTHON.bat`.

## Usage

Launch the GUI:

```bash
python py_gui_main.py
```

### Expected Data Structure

```
root_directory/
├── Group1/
│   ├── Pre1/
│   │   ├── subject01.set
│   │   └── subject02.set
│   ├── Post1/
│   │   ├── subject01.set
│   │   └── subject02.set
│   ├── Pre2/
│   └── Post2/
└── Group2/
    ├── Pre1/
    ├── Post1/
    ├── Pre2/
    └── Post2/
```

## Project Structure

```
FREQ_ANALYSIS/
├── py_gui_main.py          # Main GUI application
├── py_analyzer.py           # Core analysis engine (PSD, statistics)
├── py_data_loader.py        # EEGLAB .set file loader and validator
├── py_visualizer.py         # Publication-quality figure generation
├── py_config.py             # Configuration (bands, params, plot settings)
├── py_diagnostic.py         # Diagnostic utilities
├── show_all_markers.py      # Marker inspection utility
├── requirements_python.txt  # Python dependencies
├── INSTALL_PYTHON.bat       # Windows installer script
├── docs/                    # Development notes and documentation
└── tests/                   # Test scripts
```

## Configuration

Key parameters can be adjusted in `py_config.py` or through the GUI:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Resample Rate | 256 Hz | EEG resampling frequency |
| Epoch Length | 2.0 s | Epoch window duration |
| Frequency Range | 1-45 Hz | Analysis frequency range |
| Permutations | 1000 | Number of permutation iterations |
| Significance Alpha | 0.05 | Statistical significance threshold |
