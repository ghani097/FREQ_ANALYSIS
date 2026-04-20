"""
PyQt6 GUI for EEG Frequency Analysis
Main application window
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QLineEdit,
                             QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit,
                             QGroupBox, QFileDialog, QMessageBox, QProgressBar,
                             QCheckBox, QScrollArea, QListWidget, QListWidgetItem,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon

from py_config import DEFAULT_PARAMS, GUI_SETTINGS, FREQUENCY_BANDS
from py_data_loader import EEGDataLoader
from py_analyzer import FrequencyAnalyzer
from py_visualizer import ResultVisualizer


class AnalysisWorker(QThread):
    """Worker thread for running analysis"""
    
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    figure_created = pyqtSignal(str)  # Signal when figure is saved
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        
    def run(self):
        try:
            # Run analysis
            analyzer = FrequencyAnalyzer(self.config, self.progress.emit)
            results = analyzer.run_analysis()

            # Store detected sfreq for methods section
            if analyzer.detected_sfreq:
                self.config['detected_sfreq'] = analyzer.detected_sfreq

            # Create visualizations (saved to disk, not shown)
            visualizer = ResultVisualizer(Path(self.config['output_dir']))

            self.progress.emit("\n=== Creating figures ===")
            figure_paths = []

            def _safe_plot(label, plot_fn):
                """Run a plot function, catching errors so other plots still run."""
                try:
                    path = plot_fn()
                    if path:
                        figure_paths.append(path)
                        self.figure_created.emit(path)
                except Exception as exc:
                    self.progress.emit(f"  [FAIL] {label}: {exc}")

            # Check if individual plots are requested
            generate_individual = self.config.get('generate_individual_plots', True)

            # Check if results contain multiple session pairs
            if results and isinstance(list(results.values())[0], dict):
                # Check if first value is a band result or a comparison dict
                first_key = list(results.keys())[0]
                first_val = results[first_key]

                # If it has 'band_name' key, it's band results (single comparison)
                if 'band_name' in first_val:
                    # Single comparison (backward compatible)
                    first_result = list(results.values())[0]
                    comparison_name = None
                    if 'pre_session' in first_result and 'post_session' in first_result:
                        comparison_name = f"{first_result['post_session']}_vs_{first_result['pre_session']}"

                    # Individual band plots (if enabled)
                    if generate_individual:
                        for band_name, result in results.items():
                            self.progress.emit(f"  Creating {band_name} plot...")
                            _safe_plot(f"{band_name} topoplot",
                                       lambda r=result: visualizer.plot_band_result(r, show=False))

                    # Summary
                    self.progress.emit("  Creating summary figure...")
                    _safe_plot("summary",
                               lambda: visualizer.plot_summary(results, show=False, comparison_name=comparison_name))

                    # Statistics table
                    self.progress.emit("  Creating statistics table...")
                    _sa = self.config.get('significance_alpha', 0.05)
                    _safe_plot("statistics table",
                               lambda sa=_sa: visualizer.plot_statistics_table(results, comparison_name=comparison_name, sig_alpha=sa))

                    # Methods section
                    self.progress.emit("  Generating methods section...")
                    try:
                        methods_path = visualizer.generate_methods_section(
                            results, comparison_name=comparison_name, config=self.config
                        )
                        if methods_path:
                            self.progress.emit(f"    Methods section saved: {Path(methods_path).name}")
                    except Exception as exc:
                        self.progress.emit(f"  [FAIL] methods section: {exc}")
                else:
                    # Multiple comparisons (Post1_vs_Pre1, Post2_vs_Pre2, etc.)
                    for comparison_name, band_results in results.items():
                        if comparison_name.startswith('_'):
                            continue
                        if not band_results:
                            self.progress.emit(f"\n  === {comparison_name} === (no results, skipping)")
                            continue
                        self.progress.emit(f"\n  === {comparison_name} ===")

                        # Individual band plots (if enabled)
                        if generate_individual:
                            for band_name, result in band_results.items():
                                self.progress.emit(f"  Creating {comparison_name}/{band_name} plot...")
                                result['comparison_name'] = comparison_name
                                _safe_plot(f"{comparison_name}/{band_name}",
                                           lambda r=result: visualizer.plot_band_result(r, show=False))

                        # Summary
                        self.progress.emit(f"  Creating {comparison_name} summary...")
                        _safe_plot(f"{comparison_name} summary",
                                   lambda cn=comparison_name, br=band_results: visualizer.plot_summary(br, show=False, comparison_name=cn))

                        # Statistics table
                        self.progress.emit(f"  Creating {comparison_name} statistics table...")
                        _sa = self.config.get('significance_alpha', 0.05)
                        _safe_plot(f"{comparison_name} table",
                                   lambda cn=comparison_name, br=band_results, sa=_sa: visualizer.plot_statistics_table(br, comparison_name=cn, sig_alpha=sa))

                        # Methods section
                        self.progress.emit(f"  Generating {comparison_name} methods section...")
                        try:
                            methods_path = visualizer.generate_methods_section(
                                band_results, comparison_name=comparison_name, config=self.config
                            )
                            if methods_path:
                                self.progress.emit(f"    Methods section saved: {Path(methods_path).name}")
                        except Exception as exc:
                            self.progress.emit(f"  [FAIL] {comparison_name} methods: {exc}")

                    # Results section for all comparisons
                    self.progress.emit("\n=== Generating Publication-Ready Results Section ===")
                    try:
                        results_path = visualizer.generate_results_section(results, config=self.config)
                        if results_path:
                            self.progress.emit(f"  Results section saved: {Path(results_path).name}")
                            self.progress.emit(f"  Markdown version saved: RESULTS_SECTION.md")
                    except Exception as exc:
                        self.progress.emit(f"  [FAIL] results section: {exc}")

            # Add figure paths to results
            if isinstance(results, dict):
                results['_figure_paths'] = figure_paths
            
            self.finished.emit(results)
            
        except Exception as e:
            import traceback
            self.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


class FreqAnalysisGUI(QMainWindow):
    """Main GUI window"""
    
    def __init__(self):
        super().__init__()
        self.data_loader = None
        self.analysis_thread = None
        self.initUI()
        
    def initUI(self):
        """Initialize user interface"""
        
        self.setWindowTitle('EEG Frequency Analysis Tool - Python/MNE')
        self.setGeometry(100, 100, GUI_SETTINGS['window_width'], 
                        GUI_SETTINGS['window_height'])
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # Title
        title = QLabel('🧠 EEG Frequency Analysis Tool')
        title_font = QFont('Arial', 20, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel('Python/MNE-Python with Cluster-Based Permutation Testing')
        subtitle_font = QFont('Arial', 10)
        subtitle.setFont(subtitle_font)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(subtitle)
        
        # Section 1: Data Setup
        data_group = self._create_data_section()
        layout.addWidget(data_group)
        
        # Section 2: Analysis Parameters
        params_layout = QHBoxLayout()
        params_group = self._create_params_section()
        stats_group = self._create_stats_section()
        params_layout.addWidget(params_group)
        params_layout.addWidget(stats_group)
        layout.addLayout(params_layout)
        
        # Section 3: Output & Run
        run_group = self._create_run_section()
        layout.addWidget(run_group)
        
        # Section 4: Console Output
        console_group = self._create_console_section()
        layout.addWidget(console_group)
        
        # Status bar
        self.statusBar().showMessage('Ready')
        
    def _create_data_section(self):
        """Create data setup section"""

        group = QGroupBox("Step 1: Data Setup")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()

        # Root directory
        root_layout = QHBoxLayout()
        root_layout.addWidget(QLabel("Root Directory:"))
        self.root_dir_edit = QLineEdit()
        self.root_dir_edit.setReadOnly(True)
        self.root_dir_edit.setPlaceholderText("Select root data directory...")
        root_layout.addWidget(self.root_dir_edit)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_root_dir)
        root_layout.addWidget(self.browse_btn)
        layout.addLayout(root_layout)

        # Data structure info label
        self.structure_label = QLabel(
            "Expected structure:  root / Group / Session / *.set files    "
            "(click Scan Data after selecting directory)"
        )
        self.structure_label.setStyleSheet(
            "color: #555; font-style: italic; font-size: 10px; padding: 2px;"
        )
        self.structure_label.setWordWrap(True)
        layout.addWidget(self.structure_label)

        # Detected info
        self.groups_label = QLabel("Groups: (Select root directory)")
        self.groups_label.setStyleSheet("color: gray;")
        layout.addWidget(self.groups_label)

        self.sessions_label = QLabel("Sessions: (Will be detected)")
        self.sessions_label.setStyleSheet("color: gray;")
        layout.addWidget(self.sessions_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Data")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self.scan_data)
        btn_layout.addWidget(self.scan_btn)

        self.diagnostic_btn = QPushButton("Run Diagnostic")
        self.diagnostic_btn.setEnabled(False)
        self.diagnostic_btn.clicked.connect(self.run_diagnostic)
        btn_layout.addWidget(self.diagnostic_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Session role selection (hidden until scan)
        self.session_role_group = QGroupBox("Session Roles (select baseline and comparison sessions)")
        self.session_role_group.setStyleSheet(
            "QGroupBox { font-weight: normal; font-size: 11px; }"
        )
        self.session_role_group.setVisible(False)
        role_layout = QHBoxLayout()

        # Baseline sessions list
        baseline_col = QVBoxLayout()
        baseline_col.addWidget(QLabel("Baseline sessions:"))
        self.baseline_list = QListWidget()
        self.baseline_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.baseline_list.setMaximumHeight(80)
        baseline_col.addWidget(self.baseline_list)
        role_layout.addLayout(baseline_col)

        # Comparison sessions list
        comparison_col = QVBoxLayout()
        comparison_col.addWidget(QLabel("Comparison sessions:"))
        self.comparison_list = QListWidget()
        self.comparison_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.comparison_list.setMaximumHeight(80)
        comparison_col.addWidget(self.comparison_list)
        role_layout.addLayout(comparison_col)

        # Pairs preview
        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("Comparisons to run:"))
        self.pairs_preview_label = QLabel("")
        self.pairs_preview_label.setStyleSheet("color: #333; font-size: 10px;")
        self.pairs_preview_label.setWordWrap(True)
        preview_col.addWidget(self.pairs_preview_label)
        preview_col.addStretch()
        role_layout.addLayout(preview_col)

        self.session_role_group.setLayout(role_layout)
        layout.addWidget(self.session_role_group)

        # Connect selection changes to preview update
        self.baseline_list.itemSelectionChanged.connect(self._update_pairs_preview)
        self.comparison_list.itemSelectionChanged.connect(self._update_pairs_preview)

        group.setLayout(layout)
        return group
    
    def _populate_session_roles(self, sessions):
        """Populate baseline/comparison lists with detected sessions and auto-select"""

        self.baseline_list.clear()
        self.comparison_list.clear()

        for session in sorted(sessions):
            # Add to both lists
            baseline_item = QListWidgetItem(session)
            comparison_item = QListWidgetItem(session)
            self.baseline_list.addItem(baseline_item)
            self.comparison_list.addItem(comparison_item)

            # Auto-select: sessions with 'pre' -> baseline, with 'post' -> comparison
            if 'pre' in session.lower():
                baseline_item.setSelected(True)
            if 'post' in session.lower():
                comparison_item.setSelected(True)

        self.session_role_group.setVisible(True)
        self._update_pairs_preview()

    def _update_pairs_preview(self):
        """Update the preview of session pairs that will be analyzed"""

        baseline = [item.text() for item in self.baseline_list.selectedItems()]
        comparison = [item.text() for item in self.comparison_list.selectedItems()]

        if not baseline or not comparison:
            self.pairs_preview_label.setText("(select at least one baseline and one comparison)")
            return

        from itertools import product
        pairs = list(product(baseline, comparison))
        lines = [f"{comp} vs {base}" for base, comp in pairs]
        self.pairs_preview_label.setText(
            f"{len(pairs)} comparison(s):\n" + "\n".join(lines)
        )

    def _get_selected_sessions(self):
        """Return selected baseline and comparison sessions"""

        baseline = [item.text() for item in self.baseline_list.selectedItems()]
        comparison = [item.text() for item in self.comparison_list.selectedItems()]
        return baseline, comparison

    def _create_params_section(self):
        """Create analysis parameters section"""

        group = QGroupBox("Step 2: Analysis Parameters")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        
        # Resample rate
        resample_layout = QHBoxLayout()
        self.use_original_sfreq_check = QCheckBox("Use original sampling rate")
        self.use_original_sfreq_check.setChecked(True)
        self.use_original_sfreq_check.setToolTip(
            "Checked: Keep the original sampling rate from the data files\n"
            "Unchecked: Resample all data to the specified rate"
        )
        self.use_original_sfreq_check.stateChanged.connect(
            lambda state: self.resample_spin.setEnabled(state == 0)
        )
        resample_layout.addWidget(self.use_original_sfreq_check)
        resample_layout.addWidget(QLabel("Resample to (Hz):"))
        self.resample_spin = QSpinBox()
        self.resample_spin.setRange(64, 2048)
        self.resample_spin.setValue(256)
        self.resample_spin.setEnabled(False)  # Disabled by default (use original)
        resample_layout.addWidget(self.resample_spin)
        resample_layout.addStretch()
        layout.addLayout(resample_layout)
        
        # Epoch length
        epoch_layout = QHBoxLayout()
        epoch_layout.addWidget(QLabel("Epoch Length (s):"))
        self.epoch_spin = QDoubleSpinBox()
        self.epoch_spin.setRange(0.5, 10.0)
        self.epoch_spin.setValue(DEFAULT_PARAMS['epoch_length'])
        self.epoch_spin.setSingleStep(0.5)
        epoch_layout.addWidget(self.epoch_spin)
        epoch_layout.addStretch()
        layout.addLayout(epoch_layout)

        # Ignore epochs checkbox
        ignore_epochs_layout = QHBoxLayout()
        self.ignore_epochs_check = QCheckBox("Ignore epoch events (treat as continuous)")
        self.ignore_epochs_check.setChecked(True)
        self.ignore_epochs_check.setToolTip(
            "Checked: Concatenate all epochs into continuous data, then compute PSD\n"
            "  (simple, treats epoch boundaries as continuous signal)\n\n"
            "Unchecked: Compute PSD per epoch, then average across epochs\n"
            "  (standard EEG approach, avoids boundary artifacts)"
        )
        ignore_epochs_layout.addWidget(self.ignore_epochs_check)
        ignore_epochs_layout.addStretch()
        layout.addLayout(ignore_epochs_layout)

        # Apply EEGLAB epoch rejection checkbox
        rejection_layout = QHBoxLayout()
        self.apply_rejection_check = QCheckBox("Respect EEGLAB epoch rejection marks")
        self.apply_rejection_check.setChecked(DEFAULT_PARAMS['apply_epoch_rejection'])
        self.apply_rejection_check.setToolTip(
            "Checked (recommended): Read EEG.reject.rejmanual from each .set file\n"
            "  and exclude manually rejected bad epochs before PSD computation.\n"
            "  Matches the FieldTrip gold-standard pipeline behaviour.\n\n"
            "Unchecked: Use all epochs including manually rejected ones."
        )
        rejection_layout.addWidget(self.apply_rejection_check)
        rejection_layout.addStretch()
        layout.addLayout(rejection_layout)

        # Max epochs per subject
        max_epochs_layout = QHBoxLayout()
        max_epochs_layout.addWidget(QLabel("Max Epochs per Subject:"))
        self.max_epochs_spin = QSpinBox()
        self.max_epochs_spin.setRange(0, 5000)
        self.max_epochs_spin.setValue(DEFAULT_PARAMS['max_epochs'])
        self.max_epochs_spin.setSpecialValueText("No limit")
        self.max_epochs_spin.setToolTip(
            "Maximum number of epochs to use per subject per session (0 = no limit).\n"
            "Setting 120 matches the FieldTrip pipeline (2 min of 2-sec epochs).\n"
            "Helps equalise SNR across subjects with different epoch counts."
        )
        max_epochs_layout.addWidget(self.max_epochs_spin)
        max_epochs_layout.addStretch()
        layout.addLayout(max_epochs_layout)

        # Frequency range
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("Freq Range (Hz):"))
        self.freq_min_spin = QSpinBox()
        self.freq_min_spin.setRange(1, 100)
        self.freq_min_spin.setValue(DEFAULT_PARAMS['freq_range'][0])
        freq_layout.addWidget(self.freq_min_spin)
        freq_layout.addWidget(QLabel("-"))
        self.freq_max_spin = QSpinBox()
        self.freq_max_spin.setRange(1, 100)
        self.freq_max_spin.setValue(DEFAULT_PARAMS['freq_range'][1])
        freq_layout.addWidget(self.freq_max_spin)
        freq_layout.addStretch()
        layout.addLayout(freq_layout)
        
        # Permutations
        perm_layout = QHBoxLayout()
        perm_layout.addWidget(QLabel("Permutations:"))
        self.perm_spin = QSpinBox()
        self.perm_spin.setRange(100, 50000)
        self.perm_spin.setValue(DEFAULT_PARAMS['n_permutations'])
        self.perm_spin.setSingleStep(100)
        self.perm_spin.setToolTip("500 for testing, 1000 standard, 5000+ for publication")
        perm_layout.addWidget(self.perm_spin)
        perm_layout.addStretch()
        layout.addLayout(perm_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_stats_section(self):
        """Create statistical parameters section"""
        
        group = QGroupBox("Step 2b: Statistical Parameters")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        
        # Cluster alpha
        cluster_layout = QHBoxLayout()
        cluster_layout.addWidget(QLabel("Cluster Alpha:"))
        self.cluster_alpha_spin = QDoubleSpinBox()
        self.cluster_alpha_spin.setRange(0.001, 0.5)
        self.cluster_alpha_spin.setValue(DEFAULT_PARAMS['cluster_alpha'])
        self.cluster_alpha_spin.setSingleStep(0.01)
        self.cluster_alpha_spin.setDecimals(3)
        self.cluster_alpha_spin.setToolTip("Threshold for cluster formation (0.05 standard, 0.10 for trends)")
        cluster_layout.addWidget(self.cluster_alpha_spin)
        cluster_layout.addStretch()
        layout.addLayout(cluster_layout)
        
        # Significance alpha
        sig_layout = QHBoxLayout()
        sig_layout.addWidget(QLabel("Significance Alpha:"))
        self.sig_alpha_spin = QDoubleSpinBox()
        self.sig_alpha_spin.setRange(0.001, 0.5)
        self.sig_alpha_spin.setValue(DEFAULT_PARAMS['significance_alpha'])
        self.sig_alpha_spin.setSingleStep(0.01)
        self.sig_alpha_spin.setDecimals(3)
        self.sig_alpha_spin.setToolTip("P-value threshold for significance. Applied to both figure channel markers and table Sig column.")
        sig_layout.addWidget(self.sig_alpha_spin)
        sig_layout.addStretch()
        layout.addLayout(sig_layout)
        
        # Min neighbor channels
        neighbor_layout = QHBoxLayout()
        neighbor_layout.addWidget(QLabel("Min Neighbor Chan:"))
        self.neighbor_spin = QSpinBox()
        self.neighbor_spin.setRange(0, 10)
        self.neighbor_spin.setValue(DEFAULT_PARAMS['min_neighbor_chan'])
        self.neighbor_spin.setToolTip("Minimum adjacent channels for cluster (0 for no spatial constraint)")
        neighbor_layout.addWidget(self.neighbor_spin)
        neighbor_layout.addStretch()
        layout.addLayout(neighbor_layout)
        
        # Test type
        test_layout = QHBoxLayout()
        test_layout.addWidget(QLabel("Test Type:"))
        self.test_combo = QComboBox()
        self.test_combo.addItems(["Two-tailed", "One-tailed (positive)", "One-tailed (negative)"])
        self.test_combo.setCurrentIndex(0)
        self.test_combo.setToolTip("Two-tailed tests for both increases and decreases")
        test_layout.addWidget(self.test_combo)
        test_layout.addStretch()
        layout.addLayout(test_layout)
        
        # Statistical Method Selection
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Statistical Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Auto (Cluster if n≥5, else t-test)",
            "Cluster-Based Permutation",
            "Paired T-test + FDR",
            "Independent T-test + FDR"
        ])
        self.method_combo.setCurrentIndex(0)  # Default: Auto
        self.method_combo.setToolTip(
            "Auto: Intelligent selection based on sample size\n"
            "Cluster Permutation: Best for n≥5, spatially-aware\n"
            "Paired T-test: For within-subject comparisons\n"
            "Independent T-test: For between-group comparisons"
        )
        method_layout.addWidget(self.method_combo)
        method_layout.addStretch()
        layout.addLayout(method_layout)

        # Channel Adjacency Selection
        adj_layout = QHBoxLayout()
        adj_layout.addWidget(QLabel("Channel Adjacency:"))
        self.adjacency_combo = QComboBox()
        self.adjacency_combo.addItems([
            "MNE Standard Montage (standard_1020)",
            "Data-Based (positions in .set files)",
            "None (no spatial constraint)"
        ])
        self.adjacency_combo.setCurrentIndex(0)
        self.adjacency_combo.setToolTip(
            "MNE: Recommended — uses standard_1020 scalp positions to constrain clusters\n"
            "Data-Based: Uses electrode positions embedded in your .set files\n"
            "None: No spatial constraint (inflates null distribution, less sensitive)"
        )
        adj_layout.addWidget(self.adjacency_combo)
        adj_layout.addStretch()
        layout.addLayout(adj_layout)

        # Individual plots option
        indiv_plot_layout = QHBoxLayout()
        self.individual_plots_check = QCheckBox("Generate individual band plots")
        self.individual_plots_check.setChecked(True)  # Default: enabled
        self.individual_plots_check.setToolTip(
            "When checked: Creates separate topoplot for each frequency band\n"
            "When unchecked: Only creates summary plots (faster)"
        )
        indiv_plot_layout.addWidget(self.individual_plots_check)
        indiv_plot_layout.addStretch()
        layout.addLayout(indiv_plot_layout)
        
        # FDR correction option
        fdr_layout = QHBoxLayout()
        self.skip_fdr_check = QCheckBox("Skip FDR correction (use raw p-values)")
        self.skip_fdr_check.setChecked(False)  # Default: use FDR
        self.skip_fdr_check.setToolTip(
            "FDR (False Discovery Rate) correction adjusts p-values for multiple comparisons.\n"
            "With very small samples (n<3), FDR can be too conservative.\n"
            "Check this to use raw uncorrected p-values (NOT recommended for large samples)"
        )
        fdr_layout.addWidget(self.skip_fdr_check)
        fdr_layout.addStretch()
        layout.addLayout(fdr_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_run_section(self):
        """Create output and run section"""
        
        group = QGroupBox("Step 3: Run Analysis")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        
        # Output directory
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_edit.setPlaceholderText("Will be created in root directory...")
        output_layout.addWidget(self.output_dir_edit)
        output_browse_btn = QPushButton("Browse")
        output_browse_btn.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(output_browse_btn)
        layout.addLayout(output_layout)
        
        # Run button
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("🚀 RUN ANALYSIS")
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1B5E20;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        self.run_btn.clicked.connect(self.run_analysis)
        run_layout.addWidget(self.run_btn)
        
        self.results_btn = QPushButton("📂 View Results")
        self.results_btn.setEnabled(False)
        self.results_btn.clicked.connect(self.view_results)
        run_layout.addWidget(self.results_btn)
        
        layout.addLayout(run_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        group.setLayout(layout)
        return group
    
    def _create_console_section(self):
        """Create console output section"""
        
        group = QGroupBox("Console Output")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont('Courier', 9))
        self.console.setStyleSheet("background-color: #1E1E1E; color: #CCCCCC;")
        self.console.setMinimumHeight(200)
        layout.addWidget(self.console)
        
        group.setLayout(layout)
        return group
    
    def log(self, message: str, color: str = "white"):
        """Log message to console"""
        self.console.append(f'<span style="color:{color}">{message}</span>')
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        )
    
    def browse_root_dir(self):
        """Browse for root directory"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Data Directory")
        if dir_path:
            self.root_dir_edit.setText(dir_path)
            self.scan_btn.setEnabled(True)
            self.diagnostic_btn.setEnabled(True)
            self.log(f"Selected root directory: {dir_path}", "lightgreen")
            
            # Set default output
            self.output_dir_edit.setText(os.path.join(dir_path, "Results_Python"))
    
    def browse_output_dir(self):
        """Browse for output directory"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def scan_data(self):
        """Scan data directory"""
        root_dir = self.root_dir_edit.text()
        if not root_dir:
            return

        try:
            self.log("\n=== Scanning Data ===", "cyan")
            self.data_loader = EEGDataLoader(root_dir)
            scan_info = self.data_loader.scan_directory()

            # Update labels
            self.groups_label.setText(f"Groups: {', '.join(scan_info['groups'])}")
            self.groups_label.setStyleSheet("color: green;")

            self.sessions_label.setText(f"Sessions: {', '.join(scan_info['sessions'])}")
            self.sessions_label.setStyleSheet("color: green;")

            # Update structure info with detected layout
            groups_str = ", ".join(scan_info['groups'])
            sessions_str = ", ".join(scan_info['sessions'])
            self.structure_label.setText(
                f"Detected: {root_dir}\n"
                f"  Groups: [{groups_str}]  |  Sessions: [{sessions_str}]  |  "
                f"Files: {scan_info['total_files']} .set"
            )
            self.structure_label.setStyleSheet(
                "color: #2E7D32; font-size: 10px; padding: 2px;"
            )

            self.log(f"Found {scan_info['total_files']} .set files", "lightgreen")
            self.log(f"Groups: {', '.join(scan_info['groups'])}", "lightgreen")
            self.log(f"Sessions: {', '.join(scan_info['sessions'])}", "lightgreen")

            # Show details
            for key, subjects in scan_info['subjects'].items():
                self.log(f"  {key}: {len(subjects)} subjects")

            # Populate session role selection
            self._populate_session_roles(scan_info['sessions'])

            self.run_btn.setEnabled(True)
            self.statusBar().showMessage(f"Data scanned: {scan_info['total_files']} files found")

            QMessageBox.information(self, "Data Scan Complete",
                                  f"Found {scan_info['total_files']} .set files\n"
                                  f"Groups: {', '.join(scan_info['groups'])}\n"
                                  f"Sessions: {', '.join(scan_info['sessions'])}\n\n"
                                  f"Review session roles below, then run analysis.")

        except Exception as e:
            self.log(f"Error scanning data: {str(e)}", "red")
            QMessageBox.critical(self, "Error", f"Failed to scan data:\n{str(e)}")
    
    def run_diagnostic(self):
        """Run diagnostic checks"""
        root_dir = self.root_dir_edit.text()
        if not root_dir:
            return
        
        try:
            self.log("\n=== Running Diagnostic ===", "cyan")
            
            if not self.data_loader:
                self.data_loader = EEGDataLoader(root_dir)
                self.data_loader.scan_directory()
            
            # Validation
            validation = self.data_loader.validate_data_loading()
            
            for msg in validation['messages']:
                self.log(f"✓ {msg}", "lightgreen")
            for msg in validation['warnings']:
                self.log(f"⚠ {msg}", "yellow")
            for msg in validation['errors']:
                self.log(f"✗ {msg}", "red")
            
            # Group comparison
            self.log("\nComparing groups...", "cyan")
            comparison = self.data_loader.compare_groups_data()
            
            if 'error' in comparison:
                self.log(f"✗ {comparison['error']}", "red")
            else:
                if 'message' in comparison:
                    self.log(f"✓ {comparison['message']}", "lightgreen")
                if 'group_a' in comparison:
                    self.log(f"  Group A: {comparison['group_a']['subject']}")
                    self.log(f"    Shape: {comparison['group_a']['shape']}, "
                           f"Mean: {comparison['group_a']['mean']:.2e}")
                if 'group_b' in comparison:
                    self.log(f"  Group B: {comparison['group_b']['subject']}")
                    self.log(f"    Shape: {comparison['group_b']['shape']}, "
                           f"Mean: {comparison['group_b']['mean']:.2e}")
                if 'comparison' in comparison:
                    self.log(f"  Max difference: {comparison['comparison']['max_diff']:.2e}")
                    self.log(f"  Mean difference: {comparison['comparison']['mean_diff']:.2e}")
                    if comparison['comparison']['identical']:
                        self.log("  ⚠️ CRITICAL: Groups are IDENTICAL!", "red")
            
            self.log("\n=== Diagnostic Complete ===", "cyan")
            
        except Exception as e:
            self.log(f"✗ Diagnostic failed: {str(e)}", "red")
            QMessageBox.critical(self, "Error", f"Diagnostic failed:\n{str(e)}")
    
    def run_analysis(self):
        """Run frequency analysis"""

        # Validate session role selections
        baseline_sessions, comparison_sessions = self._get_selected_sessions()
        if not baseline_sessions or not comparison_sessions:
            QMessageBox.warning(
                self, "Session Roles Required",
                "Please select at least one baseline session and one comparison session.\n\n"
                "Use the session role lists in Step 1 to assign roles."
            )
            return

        # Map method dropdown to config
        method_map = {
            0: 'auto',           # Auto selection
            1: 'cluster',        # Force cluster permutation
            2: 'paired_ttest',   # Paired t-test + FDR
            3: 'independent_ttest'  # Independent t-test + FDR
        }
        adj_map = {
            0: 'mne',   # MNE standard_1020 montage
            1: 'data',  # Positions from .set files
            2: 'none'   # No spatial constraint
        }

        # Build config
        config = {
            'root_dir': self.root_dir_edit.text(),
            'output_dir': self.output_dir_edit.text(),
            'sessions': self.data_loader.sessions if self.data_loader else [],
            'baseline_sessions': baseline_sessions,
            'comparison_sessions': comparison_sessions,
            'resample_rate': None if self.use_original_sfreq_check.isChecked() else self.resample_spin.value(),
            'epoch_length': self.epoch_spin.value(),
            'ignore_epochs': self.ignore_epochs_check.isChecked(),
            'apply_epoch_rejection': self.apply_rejection_check.isChecked(),
            'max_epochs': self.max_epochs_spin.value() or None,
            'freq_range': (self.freq_min_spin.value(), self.freq_max_spin.value()),
            'n_permutations': self.perm_spin.value(),
            'cluster_alpha': self.cluster_alpha_spin.value(),
            'significance_alpha': self.sig_alpha_spin.value(),
            'min_neighbor_chan': self.neighbor_spin.value(),
            'tail': self.test_combo.currentIndex() - 1,  # -1, 0, 1
            'n_jobs': -1,
            'statistical_method': method_map[self.method_combo.currentIndex()],
            'adjacency_method': adj_map[self.adjacency_combo.currentIndex()],
            'process_all_session_pairs': True,
            'skip_fdr_correction': self.skip_fdr_check.isChecked(),
            'generate_individual_plots': self.individual_plots_check.isChecked()
        }
        
        # Disable controls
        self.run_btn.setEnabled(False)
        self.run_btn.setText("RUNNING...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        
        # Clear console
        self.log("\n" + "="*70, "cyan")
        self.log("STARTING ANALYSIS", "cyan")
        self.log("="*70, "cyan")
        
        # Start worker thread
        self.analysis_thread = AnalysisWorker(config)
        self.analysis_thread.progress.connect(lambda msg: self.log(msg))
        self.analysis_thread.figure_created.connect(self.on_figure_created)
        self.analysis_thread.finished.connect(self.analysis_complete)
        self.analysis_thread.error.connect(self.analysis_error)
        self.analysis_thread.start()
    
    def on_figure_created(self, fig_path: str):
        """Handle figure creation - open it in default viewer"""
        self.log(f"  ✓ Saved: {Path(fig_path).name}", "lightgreen")
        
        # Open figure in default image viewer (non-blocking)
        try:
            if sys.platform == 'win32':
                os.startfile(fig_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{fig_path}" &')
            else:
                os.system(f'xdg-open "{fig_path}" &')
        except:
            pass  # Silently fail if can't open
    
    def analysis_complete(self, results):
        """Handle analysis completion"""
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 RUN ANALYSIS")
        self.results_btn.setEnabled(True)
        
        self.log("\n" + "="*70, "lightgreen")
        self.log("✓ ANALYSIS COMPLETE!", "lightgreen")
        self.log("="*70, "lightgreen")
        
        output_dir = self.output_dir_edit.text()
        self.log(f"\nResults saved to: {output_dir}", "lightgreen")
        
        # Count figures
        n_figs = len(results.get('_figure_paths', []))
        
        QMessageBox.information(self, "Success",
                              f"Analysis completed successfully!\n\n"
                              f"Results saved to:\n{output_dir}\n\n"
                              f"{n_figs} figures created and opened.\n"
                              f"Check your image viewer or results folder.")
    
    def analysis_error(self, error_msg):
        """Handle analysis error"""
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 RUN ANALYSIS")
        
        self.log(f"\n✗ ANALYSIS FAILED: {error_msg}", "red")
        QMessageBox.critical(self, "Error", f"Analysis failed:\n\n{error_msg}")
    
    def view_results(self):
        """Open results folder"""
        output_dir = self.output_dir_edit.text()
        if output_dir and os.path.exists(output_dir):
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':
                os.system(f'open "{output_dir}"')
            else:
                os.system(f'xdg-open "{output_dir}"')


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setStyle(GUI_SETTINGS['style'])
    
    window = FreqAnalysisGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
