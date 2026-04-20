"""
Universal EEG Frequency Analysis - GUI
=======================================
PyQt6 GUI for py_freq_universal.py
Supports any number of groups and auto-detects all session pairs.

Launch: python py_gui_universal.py
"""

import sys
import os
from pathlib import Path
from itertools import product as iter_product

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QTextEdit, QGroupBox, QFileDialog, QMessageBox, QProgressBar,
    QCheckBox, QListWidget, QListWidgetItem, QAbstractItemView, QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from py_config import DEFAULT_PARAMS, GUI_SETTINGS, FREQUENCY_BANDS
from py_data_loader import EEGDataLoader
from py_freq_universal import UniversalFrequencyAnalyzer, UniversalResultVisualizer


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class UniversalAnalysisWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    figure_saved = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        try:
            # --- Analysis ---
            analyzer = UniversalFrequencyAnalyzer(self.config, self.progress.emit)
            all_results = analyzer.run_analysis()

            if analyzer.detected_sfreq:
                self.config['detected_sfreq'] = analyzer.detected_sfreq

            # --- Visualisation ---
            viz = UniversalResultVisualizer(Path(self.config['output_dir']))
            generate_individual = self.config.get('generate_individual_plots', True)
            sig_alpha = self.config.get('significance_alpha', 0.05)

            self.progress.emit("\n=== Creating figures ===")

            def _safe(label, fn):
                try:
                    path = fn()
                    if path:
                        self.figure_saved.emit(path)
                except Exception as exc:
                    self.progress.emit(f"  [FAIL] {label}: {exc}")

            for comparison_name, pair_results in all_results.items():
                if not pair_results:
                    self.progress.emit(f"  [SKIP] {comparison_name}: no results")
                    continue

                self.progress.emit(f"\n  === {comparison_name} ===")

                if generate_individual:
                    for band_name, band_result in pair_results.items():
                        self.progress.emit(f"  Creating {band_name} figure...")
                        _safe(f"{comparison_name}/{band_name}",
                              lambda r=band_result, cn=comparison_name:
                              viz.plot_band_result(r, comparison_name=cn))

                self.progress.emit(f"  Creating {comparison_name} summary...")
                _safe(f"{comparison_name} summary",
                      lambda cn=comparison_name, pr=pair_results:
                      viz.plot_summary(pr, comparison_name=cn))

                self.progress.emit(f"  Creating {comparison_name} stats table...")
                _safe(f"{comparison_name} table",
                      lambda cn=comparison_name, pr=pair_results, sa=sig_alpha:
                      viz.plot_statistics_table(pr, comparison_name=cn, sig_alpha=sa))

            self.finished.emit(all_results)

        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Main GUI window
# ---------------------------------------------------------------------------

class UniversalFreqGUI(QMainWindow):

    def __init__(self):
        super().__init__()
        self.data_loader = None
        self.analysis_thread = None
        self._detected_sessions = []
        self._initUI()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _initUI(self):
        self.setWindowTitle('EEG Frequency Analysis - Universal (N Groups / N Sessions)')
        self.setGeometry(100, 100, GUI_SETTINGS['window_width'] + 80, GUI_SETTINGS['window_height'] + 80)

        # Scrollable main area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(8)

        # Title
        title = QLabel('EEG Frequency Analysis - Universal')
        title.setFont(QFont('Arial', 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel('N Groups  |  All Session Pairs  |  Cluster-Based Permutation Testing')
        subtitle.setFont(QFont('Arial', 10))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        main_layout.addWidget(subtitle)

        # Step 1 — Data
        main_layout.addWidget(self._build_data_section())

        # Steps 2 + 2b side by side
        params_row = QHBoxLayout()
        params_row.addWidget(self._build_params_section())
        params_row.addWidget(self._build_stats_section())
        main_layout.addLayout(params_row)

        # Step 3 — Run
        main_layout.addWidget(self._build_run_section())

        # Console
        main_layout.addWidget(self._build_console_section())

        self.statusBar().showMessage('Ready')

    # ------------------------------------------------------------------
    # Step 1: Data Setup
    # ------------------------------------------------------------------

    def _build_data_section(self) -> QGroupBox:
        group = QGroupBox("Step 1: Data Setup")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout(group)

        # Root directory row
        root_row = QHBoxLayout()
        root_row.addWidget(QLabel("Root Directory:"))
        self.root_dir_edit = QLineEdit()
        self.root_dir_edit.setReadOnly(True)
        self.root_dir_edit.setPlaceholderText("Select root data directory  (root / Group / Session / *.set)")
        root_row.addWidget(self.root_dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_root)
        root_row.addWidget(browse_btn)
        layout.addLayout(root_row)

        # Structure hint
        self.structure_label = QLabel(
            "Expected: root / Group_A / Pre / Sub01.set  |  root / Group_A / Post / Sub01.set  ..."
        )
        self.structure_label.setStyleSheet("color: #555; font-style: italic; font-size: 10px;")
        self.structure_label.setWordWrap(True)
        layout.addWidget(self.structure_label)

        # Detected info
        self.groups_label = QLabel("Groups: (not yet scanned)")
        self.groups_label.setStyleSheet("color: gray;")
        layout.addWidget(self.groups_label)

        self.sessions_label = QLabel("Sessions: (not yet scanned)")
        self.sessions_label.setStyleSheet("color: gray;")
        layout.addWidget(self.sessions_label)

        # Scan / Diagnostic buttons
        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Data")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._scan_data)
        btn_row.addWidget(self.scan_btn)

        self.diag_btn = QPushButton("Run Diagnostic")
        self.diag_btn.setEnabled(False)
        self.diag_btn.clicked.connect(self._run_diagnostic)
        btn_row.addWidget(self.diag_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Session pair configuration ──────────────────────────────────────
        self.session_cfg_group = QGroupBox("Session Pair Configuration")
        self.session_cfg_group.setStyleSheet("QGroupBox { font-weight: normal; font-size: 11px; }")
        self.session_cfg_group.setVisible(False)
        sess_layout = QVBoxLayout(self.session_cfg_group)

        # Auto-detect toggle
        self.auto_detect_check = QCheckBox(
            "Auto-detect session order and run ALL ordered pairs  "
            "(recommended for 3+ sessions)")
        self.auto_detect_check.setChecked(True)
        self.auto_detect_check.setToolTip(
            "When checked: sessions are ordered automatically (Pre < During < Post, etc.)\n"
            "and every forward pair is analyzed (Pre->During, Pre->Post, During->Post).\n\n"
            "When unchecked: manually choose which sessions are baseline vs comparison."
        )
        self.auto_detect_check.stateChanged.connect(self._on_auto_detect_toggled)
        sess_layout.addWidget(self.auto_detect_check)

        # Auto-detect info widget (shown when auto=ON)
        self.auto_info_widget = QWidget()
        ai_layout = QVBoxLayout(self.auto_info_widget)
        ai_layout.setContentsMargins(20, 0, 0, 0)
        self.auto_order_label = QLabel("Detected order: —")
        self.auto_order_label.setStyleSheet("color: #2E7D32; font-size: 10px;")
        ai_layout.addWidget(self.auto_order_label)
        self.auto_pairs_label = QLabel("Pairs to run: —")
        self.auto_pairs_label.setStyleSheet("color: #2E7D32; font-size: 10px;")
        ai_layout.addWidget(self.auto_pairs_label)
        sess_layout.addWidget(self.auto_info_widget)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ccc;")
        sess_layout.addWidget(sep)

        # Manual selection widget (shown when auto=OFF)
        self.manual_widget = QWidget()
        self.manual_widget.setVisible(False)
        manual_layout = QHBoxLayout(self.manual_widget)

        baseline_col = QVBoxLayout()
        baseline_col.addWidget(QLabel("Baseline sessions:"))
        self.baseline_list = QListWidget()
        self.baseline_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.baseline_list.setMaximumHeight(80)
        self.baseline_list.itemSelectionChanged.connect(self._update_manual_preview)
        baseline_col.addWidget(self.baseline_list)
        manual_layout.addLayout(baseline_col)

        comparison_col = QVBoxLayout()
        comparison_col.addWidget(QLabel("Comparison sessions:"))
        self.comparison_list = QListWidget()
        self.comparison_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.comparison_list.setMaximumHeight(80)
        self.comparison_list.itemSelectionChanged.connect(self._update_manual_preview)
        comparison_col.addWidget(self.comparison_list)
        manual_layout.addLayout(comparison_col)

        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("Will analyze:"))
        self.manual_preview_label = QLabel("")
        self.manual_preview_label.setStyleSheet("color: #333; font-size: 10px;")
        self.manual_preview_label.setWordWrap(True)
        preview_col.addWidget(self.manual_preview_label)
        preview_col.addStretch()
        manual_layout.addLayout(preview_col)

        sess_layout.addWidget(self.manual_widget)
        layout.addWidget(self.session_cfg_group)

        return group

    # ------------------------------------------------------------------
    # Step 2: Analysis Parameters
    # ------------------------------------------------------------------

    def _build_params_section(self) -> QGroupBox:
        group = QGroupBox("Step 2: Analysis Parameters")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout(group)

        # Use original sfreq
        resample_row = QHBoxLayout()
        self.use_orig_sfreq = QCheckBox("Use original sampling rate")
        self.use_orig_sfreq.setChecked(True)
        self.use_orig_sfreq.setToolTip("Unchecked: resample all data to the specified Hz")
        self.use_orig_sfreq.stateChanged.connect(
            lambda s: self.resample_spin.setEnabled(s == 0))
        resample_row.addWidget(self.use_orig_sfreq)
        resample_row.addWidget(QLabel("Resample to (Hz):"))
        self.resample_spin = QSpinBox()
        self.resample_spin.setRange(64, 2048)
        self.resample_spin.setValue(256)
        self.resample_spin.setEnabled(False)
        resample_row.addWidget(self.resample_spin)
        resample_row.addStretch()
        layout.addLayout(resample_row)

        # Epoch length
        epoch_row = QHBoxLayout()
        epoch_row.addWidget(QLabel("Epoch Length (s):"))
        self.epoch_spin = QDoubleSpinBox()
        self.epoch_spin.setRange(0.5, 10.0)
        self.epoch_spin.setValue(DEFAULT_PARAMS['epoch_length'])
        self.epoch_spin.setSingleStep(0.5)
        epoch_row.addWidget(self.epoch_spin)
        epoch_row.addStretch()
        layout.addLayout(epoch_row)

        # Treat as continuous
        cont_row = QHBoxLayout()
        self.ignore_epochs_check = QCheckBox("Ignore epoch events (treat as continuous)")
        self.ignore_epochs_check.setChecked(True)
        self.ignore_epochs_check.setToolTip(
            "Checked: Concatenate epochs into continuous data, then Welch PSD\n"
            "Unchecked: Compute PSD per epoch, then average"
        )
        cont_row.addWidget(self.ignore_epochs_check)
        cont_row.addStretch()
        layout.addLayout(cont_row)

        # EEGLAB rejection
        rej_row = QHBoxLayout()
        self.apply_rejection_check = QCheckBox("Respect EEGLAB epoch rejection marks")
        self.apply_rejection_check.setChecked(DEFAULT_PARAMS['apply_epoch_rejection'])
        self.apply_rejection_check.setToolTip(
            "Reads EEG.reject.rejmanual from .set files and removes bad epochs.\n"
            "Recommended — matches the FieldTrip pipeline."
        )
        rej_row.addWidget(self.apply_rejection_check)
        rej_row.addStretch()
        layout.addLayout(rej_row)

        # Max epochs
        me_row = QHBoxLayout()
        me_row.addWidget(QLabel("Max Epochs per Subject:"))
        self.max_epochs_spin = QSpinBox()
        self.max_epochs_spin.setRange(0, 5000)
        self.max_epochs_spin.setValue(DEFAULT_PARAMS['max_epochs'])
        self.max_epochs_spin.setSpecialValueText("No limit")
        self.max_epochs_spin.setToolTip(
            "0 = no limit.  120 matches FieldTrip (2 min × 2-sec epochs)."
        )
        me_row.addWidget(self.max_epochs_spin)
        me_row.addStretch()
        layout.addLayout(me_row)

        # Frequency range
        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("Freq Range (Hz):"))
        self.freq_min_spin = QSpinBox()
        self.freq_min_spin.setRange(1, 200)
        self.freq_min_spin.setValue(DEFAULT_PARAMS['freq_range'][0])
        freq_row.addWidget(self.freq_min_spin)
        freq_row.addWidget(QLabel("—"))
        self.freq_max_spin = QSpinBox()
        self.freq_max_spin.setRange(1, 200)
        self.freq_max_spin.setValue(DEFAULT_PARAMS['freq_range'][1])
        freq_row.addWidget(self.freq_max_spin)
        freq_row.addStretch()
        layout.addLayout(freq_row)

        # Permutations
        perm_row = QHBoxLayout()
        perm_row.addWidget(QLabel("Permutations:"))
        self.perm_spin = QSpinBox()
        self.perm_spin.setRange(50, 50000)
        self.perm_spin.setValue(DEFAULT_PARAMS['n_permutations'])
        self.perm_spin.setSingleStep(500)
        self.perm_spin.setToolTip("50–100 for testing, 1000 standard, 5000+ for publication")
        perm_row.addWidget(self.perm_spin)
        perm_row.addStretch()
        layout.addLayout(perm_row)

        return group

    # ------------------------------------------------------------------
    # Step 2b: Statistical Parameters
    # ------------------------------------------------------------------

    def _build_stats_section(self) -> QGroupBox:
        group = QGroupBox("Step 2b: Statistical Parameters")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout(group)

        # Cluster alpha
        ca_row = QHBoxLayout()
        ca_row.addWidget(QLabel("Cluster Alpha:"))
        self.cluster_alpha_spin = QDoubleSpinBox()
        self.cluster_alpha_spin.setRange(0.001, 0.5)
        self.cluster_alpha_spin.setValue(DEFAULT_PARAMS['cluster_alpha'])
        self.cluster_alpha_spin.setSingleStep(0.01)
        self.cluster_alpha_spin.setDecimals(3)
        self.cluster_alpha_spin.setToolTip("Cluster-forming threshold (0.05 standard)")
        ca_row.addWidget(self.cluster_alpha_spin)
        ca_row.addStretch()
        layout.addLayout(ca_row)

        # Significance alpha
        sa_row = QHBoxLayout()
        sa_row.addWidget(QLabel("Significance Alpha:"))
        self.sig_alpha_spin = QDoubleSpinBox()
        self.sig_alpha_spin.setRange(0.001, 0.5)
        self.sig_alpha_spin.setValue(DEFAULT_PARAMS['significance_alpha'])
        self.sig_alpha_spin.setSingleStep(0.01)
        self.sig_alpha_spin.setDecimals(3)
        self.sig_alpha_spin.setToolTip("P-value threshold for significance markers and table")
        sa_row.addWidget(self.sig_alpha_spin)
        sa_row.addStretch()
        layout.addLayout(sa_row)

        # Min neighbor channels
        nb_row = QHBoxLayout()
        nb_row.addWidget(QLabel("Min Neighbor Chan:"))
        self.neighbor_spin = QSpinBox()
        self.neighbor_spin.setRange(0, 10)
        self.neighbor_spin.setValue(DEFAULT_PARAMS['min_neighbor_chan'])
        self.neighbor_spin.setToolTip("Minimum adjacent channels for a cluster (0 = unconstrained)")
        nb_row.addWidget(self.neighbor_spin)
        nb_row.addStretch()
        layout.addLayout(nb_row)

        # Test type
        tt_row = QHBoxLayout()
        tt_row.addWidget(QLabel("Test Type:"))
        self.test_combo = QComboBox()
        self.test_combo.addItems(["Two-tailed", "One-tailed (positive)", "One-tailed (negative)"])
        tt_row.addWidget(self.test_combo)
        tt_row.addStretch()
        layout.addLayout(tt_row)

        # Statistical method
        meth_row = QHBoxLayout()
        meth_row.addWidget(QLabel("Statistical Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Auto (Cluster if n≥5, else t-test)",
            "Cluster-Based Permutation",
            "Paired T-test + FDR",
            "Independent T-test + FDR",
        ])
        self.method_combo.setToolTip(
            "Auto: cluster if n≥5, else independent t-test with FDR\n"
            "Cluster: best for n≥5, spatially-aware\n"
            "Paired / Independent t-test: FDR-corrected channel-wise tests"
        )
        meth_row.addWidget(self.method_combo)
        meth_row.addStretch()
        layout.addLayout(meth_row)

        # Adjacency
        adj_row = QHBoxLayout()
        adj_row.addWidget(QLabel("Channel Adjacency:"))
        self.adjacency_combo = QComboBox()
        self.adjacency_combo.addItems([
            "MNE Standard Montage (standard_1020)",
            "Data-Based (positions in .set files)",
            "None (no spatial constraint)",
        ])
        self.adjacency_combo.setToolTip(
            "MNE: recommended — uses standard_1020 scalp positions\n"
            "Data: uses electrode positions from your .set files\n"
            "None: no spatial constraint (wider null distribution)"
        )
        adj_row.addWidget(self.adjacency_combo)
        adj_row.addStretch()
        layout.addLayout(adj_row)

        # Individual band plots
        ip_row = QHBoxLayout()
        self.individual_plots_check = QCheckBox("Generate individual band plots")
        self.individual_plots_check.setChecked(True)
        self.individual_plots_check.setToolTip(
            "Creates a separate topomap figure for each frequency band.\n"
            "Uncheck to only produce summary figures (faster)."
        )
        ip_row.addWidget(self.individual_plots_check)
        ip_row.addStretch()
        layout.addLayout(ip_row)

        # Skip FDR
        fdr_row = QHBoxLayout()
        self.skip_fdr_check = QCheckBox("Skip FDR correction (raw p-values)")
        self.skip_fdr_check.setChecked(False)
        self.skip_fdr_check.setToolTip(
            "Only affects the t-test fallback path.\n"
            "Not recommended for large samples."
        )
        fdr_row.addWidget(self.skip_fdr_check)
        fdr_row.addStretch()
        layout.addLayout(fdr_row)

        return group

    # ------------------------------------------------------------------
    # Step 3: Run
    # ------------------------------------------------------------------

    def _build_run_section(self) -> QGroupBox:
        group = QGroupBox("Step 3: Run Analysis")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout(group)

        # Output directory
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setReadOnly(True)
        self.output_dir_edit.setPlaceholderText("Will be created inside root directory...")
        out_row.addWidget(self.output_dir_edit)
        out_browse_btn = QPushButton("Browse")
        out_browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(out_browse_btn)
        layout.addLayout(out_row)

        # Run / View buttons
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("RUN ANALYSIS")
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #1565C0;
                color: white; font-weight: bold; font-size: 14px;
                padding: 10px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #0D47A1; }
            QPushButton:disabled { background-color: #BBDEFB; color: #999; }
        """)
        self.run_btn.clicked.connect(self._run_analysis)
        btn_row.addWidget(self.run_btn)

        self.results_btn = QPushButton("View Results Folder")
        self.results_btn.setEnabled(False)
        self.results_btn.clicked.connect(self._view_results)
        btn_row.addWidget(self.results_btn)
        layout.addLayout(btn_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        return group

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    def _build_console_section(self) -> QGroupBox:
        group = QGroupBox("Console Output")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layout = QVBoxLayout(group)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont('Courier', 9))
        self.console.setStyleSheet("background-color: #1E1E1E; color: #CCCCCC;")
        self.console.setMinimumHeight(200)
        layout.addWidget(self.console)
        return group

    # ------------------------------------------------------------------
    # Helpers / slots
    # ------------------------------------------------------------------

    def _log(self, message: str, color: str = "white"):
        self.console.append(f'<span style="color:{color}">{message}</span>')
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum())

    def _browse_root(self):
        path = QFileDialog.getExistingDirectory(self, "Select Root Data Directory")
        if path:
            self.root_dir_edit.setText(path)
            self.scan_btn.setEnabled(True)
            self.diag_btn.setEnabled(True)
            self.output_dir_edit.setText(os.path.join(path, "RESULTS_UNIVERSAL"))
            self._log(f"Selected: {path}", "lightgreen")

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.output_dir_edit.setText(path)

    def _on_auto_detect_toggled(self, state: int):
        is_auto = (state == Qt.CheckState.Checked.value or state == 2)
        self.auto_info_widget.setVisible(is_auto)
        self.manual_widget.setVisible(not is_auto)
        self._refresh_session_display()

    def _refresh_session_display(self):
        """Refresh the auto-detect info labels using the current sessions."""
        if not self._detected_sessions:
            return
        if self.auto_detect_check.isChecked():
            order = self._auto_sorted_sessions(self._detected_sessions)
            self.auto_order_label.setText("Detected order:  " + "  →  ".join(order))
            pairs = [f"{a} → {b}"
                     for i, a in enumerate(order)
                     for b in order[i + 1:]]
            self.auto_pairs_label.setText("Pairs to run:  " + ",   ".join(pairs))

    def _auto_sorted_sessions(self, sessions):
        """Sort sessions using the same heuristic as UniversalFrequencyAnalyzer."""
        ORDER_KEYS = [
            ('pre', 0), ('baseline', 0), ('rest', 0),
            ('during', 1), ('intra', 1), ('mid', 1), ('stim', 1), ('active', 1),
            ('post', 2),
            ('follow', 3), ('fu', 3),
            ('w1', 4), ('w2', 5), ('w4', 6), ('w6', 7), ('w8', 8),
        ]

        def rank(s):
            sl = s.lower()
            for key, r in ORDER_KEYS:
                if key in sl:
                    return (r, sl)
            return (99, sl)

        return sorted(sessions, key=rank)

    def _populate_session_roles(self, sessions):
        self._detected_sessions = list(sessions)

        # Populate manual lists
        self.baseline_list.clear()
        self.comparison_list.clear()
        for s in sorted(sessions):
            bi = QListWidgetItem(s)
            ci = QListWidgetItem(s)
            self.baseline_list.addItem(bi)
            self.comparison_list.addItem(ci)
            if 'pre' in s.lower():
                bi.setSelected(True)
            if 'post' in s.lower():
                ci.setSelected(True)

        self._refresh_session_display()
        self.session_cfg_group.setVisible(True)
        self._update_manual_preview()

    def _update_manual_preview(self):
        baseline = [item.text() for item in self.baseline_list.selectedItems()]
        comparison = [item.text() for item in self.comparison_list.selectedItems()]
        if not baseline or not comparison:
            self.manual_preview_label.setText("(select at least one baseline and one comparison)")
            return
        pairs = list(iter_product(baseline, comparison))
        lines = [f"{comp} vs {base}" for base, comp in pairs]
        self.manual_preview_label.setText(f"{len(pairs)} pair(s):\n" + "\n".join(lines))

    def _scan_data(self):
        root_dir = self.root_dir_edit.text()
        if not root_dir:
            return
        try:
            self._log("\n=== Scanning Data ===", "cyan")
            self.data_loader = EEGDataLoader(root_dir)
            info = self.data_loader.scan_directory()

            self.groups_label.setText(f"Groups: {', '.join(info['groups'])}")
            self.groups_label.setStyleSheet("color: green; font-weight: bold;")
            self.sessions_label.setText(f"Sessions: {', '.join(info['sessions'])}")
            self.sessions_label.setStyleSheet("color: green;")

            self.structure_label.setText(
                f"Detected:  {len(info['groups'])} groups  |  "
                f"{len(info['sessions'])} sessions  |  "
                f"{info['total_files']} .set files"
            )
            self.structure_label.setStyleSheet("color: #1B5E20; font-size: 10px;")

            self._log(f"Groups: {', '.join(info['groups'])}", "lightgreen")
            self._log(f"Sessions: {', '.join(info['sessions'])}", "lightgreen")
            for key, subjects in info['subjects'].items():
                self._log(f"  {key}: {len(subjects)} subjects")

            self._populate_session_roles(info['sessions'])
            self.run_btn.setEnabled(True)
            self.statusBar().showMessage(
                f"Scanned: {len(info['groups'])} groups, {len(info['sessions'])} sessions, "
                f"{info['total_files']} files")

            QMessageBox.information(
                self, "Scan Complete",
                f"Found {info['total_files']} .set files\n"
                f"Groups ({len(info['groups'])}): {', '.join(info['groups'])}\n"
                f"Sessions ({len(info['sessions'])}): {', '.join(info['sessions'])}\n\n"
                "Review session pair configuration, then click RUN ANALYSIS."
            )
        except Exception as exc:
            self._log(f"Scan failed: {exc}", "red")
            QMessageBox.critical(self, "Error", f"Failed to scan data:\n{exc}")

    def _run_diagnostic(self):
        root_dir = self.root_dir_edit.text()
        if not root_dir:
            return
        try:
            self._log("\n=== Running Diagnostic ===", "cyan")
            if not self.data_loader:
                self.data_loader = EEGDataLoader(root_dir)
                self.data_loader.scan_directory()

            val = self.data_loader.validate_data_loading()
            for m in val['messages']:
                self._log(f"  OK  {m}", "lightgreen")
            for m in val['warnings']:
                self._log(f"  !! {m}", "yellow")
            for m in val['errors']:
                self._log(f"  XX {m}", "red")

            comp = self.data_loader.compare_groups_data()
            if 'error' in comp:
                self._log(f"  XX {comp['error']}", "red")
            else:
                if 'message' in comp:
                    self._log(f"  OK  {comp['message']}", "lightgreen")
                for gkey in ('group_a', 'group_b'):
                    if gkey in comp:
                        g = comp[gkey]
                        self._log(f"  {gkey}: {g['subject']}  shape={g['shape']}  "
                                  f"mean={g['mean']:.2e}")
                if 'comparison' in comp:
                    self._log(f"  Max diff: {comp['comparison']['max_diff']:.2e}")
                    if comp['comparison']['identical']:
                        self._log("  !! CRITICAL: groups are IDENTICAL!", "red")

            self._log("=== Diagnostic Complete ===", "cyan")
        except Exception as exc:
            self._log(f"Diagnostic failed: {exc}", "red")
            QMessageBox.critical(self, "Error", f"Diagnostic failed:\n{exc}")

    def _run_analysis(self):
        """Build config and start worker thread."""
        root_dir = self.root_dir_edit.text()
        output_dir = self.output_dir_edit.text()
        if not root_dir or not output_dir:
            QMessageBox.warning(self, "Missing paths",
                                "Please select a root directory and output directory.")
            return

        # Session config
        use_auto = self.auto_detect_check.isChecked()
        if use_auto:
            baseline_sessions = []
            comparison_sessions = []
        else:
            baseline_sessions = [i.text() for i in self.baseline_list.selectedItems()]
            comparison_sessions = [i.text() for i in self.comparison_list.selectedItems()]
            if not baseline_sessions or not comparison_sessions:
                QMessageBox.warning(
                    self, "Session selection required",
                    "Please select at least one baseline session and one comparison session,\n"
                    "or enable Auto-detect."
                )
                return

        method_map = {0: 'auto', 1: 'cluster', 2: 'paired_ttest', 3: 'independent_ttest'}
        adj_map = {0: 'mne', 1: 'data', 2: 'none'}

        config = {
            'root_dir': root_dir,
            'output_dir': output_dir,
            'sessions': self.data_loader.sessions if self.data_loader else [],
            'baseline_sessions': baseline_sessions,
            'comparison_sessions': comparison_sessions,
            'resample_rate': None if self.use_orig_sfreq.isChecked() else self.resample_spin.value(),
            'epoch_length': self.epoch_spin.value(),
            'ignore_epochs': self.ignore_epochs_check.isChecked(),
            'apply_epoch_rejection': self.apply_rejection_check.isChecked(),
            'max_epochs': self.max_epochs_spin.value() or None,
            'freq_range': (self.freq_min_spin.value(), self.freq_max_spin.value()),
            'n_permutations': self.perm_spin.value(),
            'cluster_alpha': self.cluster_alpha_spin.value(),
            'significance_alpha': self.sig_alpha_spin.value(),
            'min_neighbor_chan': self.neighbor_spin.value(),
            'tail': self.test_combo.currentIndex() - 1,  # -1=neg, 0=two, 1=pos
            'n_jobs': -1,
            'statistical_method': method_map[self.method_combo.currentIndex()],
            'adjacency_method': adj_map[self.adjacency_combo.currentIndex()],
            'skip_fdr_correction': self.skip_fdr_check.isChecked(),
            'generate_individual_plots': self.individual_plots_check.isChecked(),
        }

        # Lock UI
        self.run_btn.setEnabled(False)
        self.run_btn.setText("RUNNING...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self._log("\n" + "=" * 70, "cyan")
        self._log("STARTING UNIVERSAL ANALYSIS", "cyan")
        if use_auto:
            order = self._auto_sorted_sessions(self._detected_sessions)
            self._log(f"Session order: {' → '.join(order)}", "cyan")
        else:
            self._log(f"Baseline: {baseline_sessions}  |  Comparison: {comparison_sessions}", "cyan")
        self._log("=" * 70, "cyan")

        self.analysis_thread = UniversalAnalysisWorker(config)
        self.analysis_thread.progress.connect(self._on_progress)
        self.analysis_thread.figure_saved.connect(self._on_figure_saved)
        self.analysis_thread.finished.connect(self._on_finished)
        self.analysis_thread.error.connect(self._on_error)
        self.analysis_thread.start()

    def _on_progress(self, msg: str):
        # Colour-code based on content
        if any(k in msg for k in ('[OK]', 'Loaded', 'Detected', 'complete', 'Done')):
            color = 'lightgreen'
        elif any(k in msg for k in ('[FAIL]', 'CRITICAL', 'ERROR', 'failed')):
            color = 'red'
        elif any(k in msg for k in ('[WARNING]', 'WARNING', 'Warning')):
            color = 'yellow'
        elif msg.startswith('===') or msg.startswith('---'):
            color = 'cyan'
        else:
            color = 'white'
        self._log(msg, color)

    def _on_figure_saved(self, path: str):
        self._log(f"  Saved: {Path(path).name}", "lightgreen")
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f'open "{path}" &')
            else:
                os.system(f'xdg-open "{path}" &')
        except Exception:
            pass

    def _on_finished(self, results: dict):
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("RUN ANALYSIS")
        self.results_btn.setEnabled(True)

        n_comparisons = len([k for k, v in results.items()
                             if isinstance(v, dict) and v])
        n_bands_total = sum(len(v) for v in results.values()
                            if isinstance(v, dict))

        self._log("\n" + "=" * 70, "lightgreen")
        self._log("ANALYSIS COMPLETE", "lightgreen")
        self._log("=" * 70, "lightgreen")
        self._log(f"Results saved to: {self.output_dir_edit.text()}", "lightgreen")

        QMessageBox.information(
            self, "Complete",
            f"Analysis finished successfully!\n\n"
            f"Session pairs analysed: {n_comparisons}\n"
            f"Total band results: {n_bands_total}\n\n"
            f"Results saved to:\n{self.output_dir_edit.text()}"
        )

    def _on_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("RUN ANALYSIS")
        self._log(f"\nFAILED:\n{msg}", "red")
        QMessageBox.critical(self, "Analysis Failed", f"Error:\n\n{msg[:600]}")

    def _view_results(self):
        path = self.output_dir_edit.text()
        if path and os.path.exists(path):
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle(GUI_SETTINGS['style'])
    win = UniversalFreqGUI()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
