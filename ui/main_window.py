from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .controller import PipelineController, TransformSnapshot
from .explain_dialog import ExplainDialog
from .json_highlighter import JsonHighlighter


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _TransformTask(QRunnable):
    def __init__(self, controller: PipelineController, input_path: str) -> None:
        super().__init__()
        self.controller = controller
        self.input_path = input_path
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            snapshot = self.controller.transform(self.input_path, explain=True)
        except Exception as exc:  # pragma: no cover - surfaced in GUI
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(snapshot)


class MainWindow(QMainWindow):
    def __init__(self, controller: PipelineController | None = None) -> None:
        super().__init__()
        self.controller = controller or PipelineController()
        self.thread_pool = QThreadPool.globalInstance()
        self.snapshot: TransformSnapshot | None = None

        self.setWindowTitle("Multi-Source Candidate Transformer")
        self.resize(1000, 700)

        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Select an input folder...")
        self.input_path.setReadOnly(True)

        self.browse_button = QPushButton("Browse Folder")
        self.transform_button = QPushButton("Transform")
        self.download_json_button = QPushButton("Download JSON")
        self.download_csv_button = QPushButton("Download CSV")
        self.explain_button = QPushButton("Explain")

        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = JsonHighlighter(self.viewer.document())
        self._active_task: _TransformTask | None = None

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        self._build_ui()
        self._bind_events()
        self._set_actions_enabled(False)

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Input Folder"))
        folder_row.addWidget(self.input_path, 1)
        folder_row.addWidget(self.browse_button)
        layout.addLayout(folder_row)

        layout.addWidget(self.transform_button)
        layout.addWidget(self.viewer, 1)

        button_row = QHBoxLayout()
        button_row.addWidget(self.download_json_button)
        button_row.addWidget(self.download_csv_button)
        button_row.addWidget(self.explain_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.setCentralWidget(central)

    def _bind_events(self) -> None:
        self.browse_button.clicked.connect(self._browse_folder)
        self.transform_button.clicked.connect(self._run_transform)
        self.download_json_button.clicked.connect(self._download_json)
        self.download_csv_button.clicked.connect(self._download_csv)
        self.explain_button.clicked.connect(self._show_explain_dialog)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.download_json_button.setEnabled(enabled)
        self.download_csv_button.setEnabled(enabled)
        self.explain_button.setEnabled(enabled)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select input folder")
        if folder:
            self.input_path.setText(folder)

    def _run_transform(self) -> None:
        input_path = self.input_path.text().strip()
        if not input_path:
            QMessageBox.information(self, "Select input", "Please choose an input folder first.")
            return
        self.status.showMessage("Processing...")
        self.transform_button.setEnabled(False)
        self._set_actions_enabled(False)
        task = _TransformTask(self.controller, input_path)
        task.signals.finished.connect(self._on_transform_finished)
        task.signals.failed.connect(self._on_transform_failed)
        self._active_task = task
        self.thread_pool.start(task)

    @Slot(object)
    def _on_transform_finished(self, snapshot: TransformSnapshot) -> None:
        self.snapshot = snapshot
        self._active_task = None
        self.viewer.setPlainText(snapshot.json_text)
        self.status.showMessage("Processing Complete")
        self.transform_button.setEnabled(True)
        self._set_actions_enabled(True)

    @Slot(str)
    def _on_transform_failed(self, message: str) -> None:
        self.transform_button.setEnabled(True)
        self._active_task = None
        self.status.showMessage("Processing failed")
        QMessageBox.critical(self, "Transform failed", message)

    def _download_json(self) -> None:
        if not self.snapshot:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "output.json", "JSON Files (*.json)")
        if path:
            self.controller.save_json(self.snapshot, path)
            self.status.showMessage(f"Saved JSON to {path}")

    def _download_csv(self) -> None:
        if not self.snapshot:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "output.csv", "CSV Files (*.csv)")
        if path:
            self.controller.save_csv(self.snapshot, path)
            self.status.showMessage(f"Saved CSV to {path}")

    def _show_explain_dialog(self) -> None:
        if not self.snapshot:
            return
        dialog = ExplainDialog(self.snapshot.report_payload, self)
        dialog.exec()
