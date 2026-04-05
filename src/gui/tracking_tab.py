import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QFormLayout, 
    QCheckBox, QMessageBox, QProgressBar
)
from PyQt6.QtCore import QThread, pyqtSignal
from ..core.tracker import BallTracker, TrackerConfig
from .mpl_widget import MplWidget

class TrackingThread(QThread):
    finished = pyqtSignal(tuple) # times, positions, fit, inliers, folder_name
    error = pyqtSignal(str)

    def __init__(self, folder_path, config):
        super().__init__()
        self.folder_path = folder_path
        self.config = config

    def run(self):
        try:
            tracker = BallTracker(self.config)
            detections = tracker.process_images(self.folder_path)
            if not detections:
                self.error.emit("No valid images found in the selected folder.")
                return
            
            times, positions, fit, inliers = tracker.calculate_speed_fit(detections)
            folder_name = os.path.basename(self.folder_path)
            self.finished.emit((times, positions, fit, inliers, folder_name))
        except Exception as e:
            self.error.emit(str(e))

class TrackingTab(QWidget):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.init_ui()

    def init_ui(self):
        self.layout = QHBoxLayout(self)

        # Left Panel: Controls
        self.controls = QWidget()
        self.controls.setFixedWidth(300)
        self.form_layout = QFormLayout(self.controls)

        self.folder_path_le = QLineEdit()
        self.browse_btn = QPushButton("Browse TIFF Folder")
        self.browse_btn.clicked.connect(self.on_browse)

        self.pixel_to_cm_le = QLineEdit("108.3")
        self.strictness_le = QLineEdit("1.0")
        self.use_robust_cb = QCheckBox("Use Robust Regression (RANSAC)")
        self.use_robust_cb.setChecked(True)
        
        self.smooth_window_le = QLineEdit("5")
        self.smooth_polyorder_le = QLineEdit("2")

        self.start_btn = QPushButton("Start Video Analysis")
        self.start_btn.clicked.connect(self.on_start)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 40px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()

        self.form_layout.addRow(self.browse_btn)
        self.form_layout.addRow("Folder:", self.folder_path_le)
        self.form_layout.addRow("Pixels per cm:", self.pixel_to_cm_le)
        self.form_layout.addRow("RANSAC Strictness:", self.strictness_le)
        self.form_layout.addRow(self.use_robust_cb)
        self.form_layout.addRow("Smooth Window:", self.smooth_window_le)
        self.form_layout.addRow("Smooth Order:", self.smooth_polyorder_le)
        self.form_layout.addRow(self.start_btn)
        self.form_layout.addRow(self.progress_bar)

        # Right Panel: Plot
        self.plot_widget = MplWidget()

        self.layout.addWidget(self.controls)
        self.layout.addWidget(self.plot_widget)

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select TIFF Folder")
        if folder:
            self.folder_path_le.setText(folder)

    def on_start(self):
        folder = self.folder_path_le.text()
        if not os.path.isdir(folder):
            QMessageBox.critical(self, "Error", "Please select a valid folder.")
            return

        try:
            config = TrackerConfig(
                pixel_to_cm=float(self.pixel_to_cm_le.text()),
                strictness=float(self.strictness_le.text()),
                use_robust=self.use_robust_cb.isChecked(),
                smooth_window=int(self.smooth_window_le.text()),
                smooth_polyorder=int(self.smooth_polyorder_le.text())
            )
        except ValueError as e:
            QMessageBox.critical(self, "Error", f"Invalid parameters: {e}")
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.show()
        
        self.thread = TrackingThread(folder, config)
        self.thread.finished.connect(self.on_finished)
        self.thread.error.connect(self.on_error)
        self.thread.start()

    def on_finished(self, results):
        self.start_btn.setEnabled(True)
        self.progress_bar.hide()
        
        times, positions, fit, inliers, folder_name = results
        self.plot_results(times, positions, fit, inliers, folder_name)

    def on_error(self, message):
        self.start_btn.setEnabled(True)
        self.progress_bar.hide()
        QMessageBox.critical(self, "Error", f"Analysis failed: {message}")

    def plot_results(self, times, positions, fit, inliers, folder_name):
        self.plot_widget.clear()
        ax = self.plot_widget.ax
        
        if self.use_robust_cb.isChecked() and inliers is not None:
            ax.scatter(times[inliers], positions[inliers], label="Inliers", marker="o", alpha=0.6)
            ax.scatter(times[~inliers], positions[~inliers], label="Outliers", marker="x", alpha=0.6)
        else:
            ax.scatter(times, positions, label="Data", marker="o", alpha=0.6)

        t_fit = [min(times), max(times)]
        y_fit = [fit['slope'] * t + fit['intercept'] for t in t_fit]
        ax.plot(t_fit, y_fit, color='red', label='Fit', lw=2)

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Position (cm)")
        ax.set_title(f"Ball Trajectory: {folder_name}")
        
        annot = (
            f"Speed = {fit['slope']:.4f} ± {fit['stderr']:.4f} cm/s\n"
            f"R² = {fit['r_value']**2:.4f}"
        )
        ax.text(0.05, 0.95, annot, transform=ax.transAxes, va="top",
                bbox=dict(facecolor="white", alpha=0.7))
        
        ax.legend()
        ax.grid(True)
        self.plot_widget.canvas.draw()
