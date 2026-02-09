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
                             QCheckBox, QScrollArea)
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
            
            # Create visualizations (saved to disk, not shown)
            visualizer = ResultVisualizer(Path(self.config['output_dir']))

            self.progress.emit("\n=== Creating figures ===")
            figure_paths = []

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
                    # Try to get comparison name from first result
                    first_result = list(results.values())[0]
                    comparison_name = None
                    if 'pre_session' in first_result and 'post_session' in first_result:
                        comparison_name = f"{first_result['post_session']}_vs_{first_result['pre_session']}"

                    # Individual band plots (if enabled)
                    if generate_individual:
                        for band_name, result in results.items():
                            self.progress.emit(f"  Creating {band_name} plot...")
                            fig_path = visualizer.plot_band_result(result, show=False)
                            figure_paths.append(fig_path)
                            self.figure_created.emit(fig_path)

                    # Create summary with comparison name
                    self.progress.emit("  Creating summary figure...")
                    summary_path = visualizer.plot_summary(results, show=False, comparison_name=comparison_name)
                    if summary_path:
                        figure_paths.append(summary_path)
                        self.figure_created.emit(summary_path)

                    # Create statistics table
                    self.progress.emit("  Creating statistics table...")
                    table_path = visualizer.plot_statistics_table(results, comparison_name=comparison_name)
                    if table_path:
                        figure_paths.append(table_path)
                        self.figure_created.emit(table_path)

                    # Generate methods section
                    self.progress.emit("  Generating methods section...")
                    methods_path = visualizer.generate_methods_section(
                        results, comparison_name=comparison_name, config=self.config
                    )
                    if methods_path:
                        self.progress.emit(f"    Methods section saved: {Path(methods_path).name}")
                else:
                    # Multiple comparisons (Post1_vs_Pre1, Post2_vs_Pre2, etc.)
                    for comparison_name, band_results in results.items():
                        self.progress.emit(f"\n  === {comparison_name} ===")

                        # Individual band plots (if enabled)
                        if generate_individual:
                            for band_name, result in band_results.items():
                                self.progress.emit(f"  Creating {comparison_name}/{band_name} plot...")
                                # Add comparison name to result for filename
                                result['comparison_name'] = comparison_name
                                fig_path = visualizer.plot_band_result(result, show=False)
                                figure_paths.append(fig_path)
                                self.figure_created.emit(fig_path)

                        # Create summary for this comparison
                        self.progress.emit(f"  Creating {comparison_name} summary...")
                        summary_path = visualizer.plot_summary(band_results, show=False, comparison_name=comparison_name)
                        if summary_path:
                            figure_paths.append(summary_path)
                            self.figure_created.emit(summary_path)

                        # Create statistics table for this comparison
                        self.progress.emit(f"  Creating {comparison_name} statistics table...")
                        table_path = visualizer.plot_statistics_table(band_results, comparison_name=comparison_name)
                        if table_path:
                            figure_paths.append(table_path)
                            self.figure_created.emit(table_path)

                        # Generate methods section
                        self.progress.emit(f"  Generating {comparison_name} methods section...")
                        methods_path = visualizer.generate_methods_section(
                            band_results, comparison_name=comparison_name, config=self.config
                        )
                        if methods_path:
                            self.progress.emit(f"    Methods section saved: {Path(methods_path).name}")

                    # Generate complete results section for all comparisons
                    self.progress.emit("\n=== Generating Publication-Ready Results Section ===")
                    results_path = visualizer.generate_results_section(results, config=self.config)
                    if results_path:
                        self.progress.emit(f"  Results section saved: {Path(results_path).name}")
                        self.progress.emit(f"  Markdown version saved: RESULTS_SECTION.md")

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
        
        # Detected info
        self.groups_label = QLabel("Groups: (Select root directory)")
        self.groups_label.setStyleSheet("color: gray;")
        layout.addWidget(self.groups_label)
        
        self.sessions_label = QLabel("Sessions: (Will be detected)")
        self.sessions_label.setStyleSheet("color: gray;")
        layout.addWidget(self.sessions_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("🔍 Scan Data")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self.scan_data)
        btn_layout.addWidget(self.scan_btn)
        
        self.diagnostic_btn = QPushButton("🔧 Run Diagnostic")
        self.diagnostic_btn.setEnabled(False)
        self.diagnostic_btn.clicked.connect(self.run_diagnostic)
        btn_layout.addWidget(self.diagnostic_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_params_section(self):
        """Create analysis parameters section"""
        
        group = QGroupBox("Step 2: Analysis Parameters")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout()
        
        # Resample rate
        resample_layout = QHBoxLayout()
        resample_layout.addWidget(QLabel("Resample Rate (Hz):"))
        self.resample_spin = QSpinBox()
        self.resample_spin.setRange(64, 2048)
        self.resample_spin.setValue(DEFAULT_PARAMS['resample_rate'])
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
        self.sig_alpha_spin.setToolTip("P-value threshold (0.05 standard, 0.10 to see trends)")
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
        
        # Session pair processing option
        session_layout = QHBoxLayout()
        self.all_pairs_check = QCheckBox("Process all session pairs (Pre1/Post1, Pre2/Post2, etc.)")
        self.all_pairs_check.setChecked(True)  # Default: enabled
        self.all_pairs_check.setToolTip(
            "When checked: Analyzes all Pre/Post pairs found in data\n"
            "When unchecked: Only analyzes the first Pre/Post pair (legacy behavior)"
        )
        session_layout.addWidget(self.all_pairs_check)
        session_layout.addStretch()
        layout.addLayout(session_layout)

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
            
            self.log(f"✓ Found {scan_info['total_files']} .set files", "lightgreen")
            self.log(f"✓ Groups: {', '.join(scan_info['groups'])}", "lightgreen")
            self.log(f"✓ Sessions: {', '.join(scan_info['sessions'])}", "lightgreen")
            
            # Show details
            for key, subjects in scan_info['subjects'].items():
                self.log(f"  {key}: {len(subjects)} subjects")
            
            self.run_btn.setEnabled(True)
            self.statusBar().showMessage(f"Data scanned: {scan_info['total_files']} files found")
            
            QMessageBox.information(self, "Data Scan Complete",
                                  f"Found {scan_info['total_files']} .set files\n"
                                  f"Groups: {', '.join(scan_info['groups'])}\n"
                                  f"Sessions: {', '.join(scan_info['sessions'])}")
            
        except Exception as e:
            self.log(f"✗ Error scanning data: {str(e)}", "red")
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
        
        # Map method dropdown to config
        method_map = {
            0: 'auto',           # Auto selection
            1: 'cluster',        # Force cluster permutation
            2: 'paired_ttest',   # Paired t-test + FDR
            3: 'independent_ttest'  # Independent t-test + FDR
        }
        
        # Build config
        config = {
            'root_dir': self.root_dir_edit.text(),
            'output_dir': self.output_dir_edit.text(),
            'sessions': self.data_loader.sessions if self.data_loader else [],
            'resample_rate': self.resample_spin.value(),
            'epoch_length': self.epoch_spin.value(),
            'freq_range': (self.freq_min_spin.value(), self.freq_max_spin.value()),
            'n_permutations': self.perm_spin.value(),
            'cluster_alpha': self.cluster_alpha_spin.value(),
            'significance_alpha': self.sig_alpha_spin.value(),
            'min_neighbor_chan': self.neighbor_spin.value(),
            'tail': self.test_combo.currentIndex() - 1,  # -1, 0, 1
            'n_jobs': -1,
            'statistical_method': method_map[self.method_combo.currentIndex()],
            'process_all_session_pairs': self.all_pairs_check.isChecked(),
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
