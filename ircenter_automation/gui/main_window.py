import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from ..documents import find_document, parse_document
from ..errors import WorkflowError
from ..normalization import parse_child_name
from ..settings import load_settings
from ..workflow import ReviewSummary, Workflow


class Worker(QThread):
    status = Signal(str)
    authentication_needed = Signal()
    review_ready = Signal(object)
    outcome = Signal(str)
    failed = Signal(str)

    def __init__(self, settings_path: Path, name: str):
        super().__init__()
        self.settings_path = settings_path
        self.name = name
        self.stop_event = Event()
        self.continue_event = Event()
        self.submit_event = Event()

    def run(self) -> None:
        try:
            workflow = Workflow(load_settings(self.settings_path), self.status.emit,
                                self.authentication_needed.emit, self.review_ready.emit,
                                self.stop_event, self.continue_event, self.submit_event)
            self.outcome.emit(workflow.run(self.name))
        except WorkflowError as exc:
            self.failed.emit(str(exc))
        except Exception:
            # Browser/library exceptions may contain page contents; never display or log them.
            self.failed.emit("Unexpected browser or application error. Nothing will be submitted automatically; inspect the site manually.")

    def stop(self) -> None:
        self.stop_event.set()
        self.continue_event.set()
        self.submit_event.set()


class MainWindow(QMainWindow):
    def __init__(self, settings_path: Path):
        super().__init__()
        self.settings_path = settings_path
        self.worker: Worker | None = None
        self.setWindowTitle("IR Center — Local DOCX form assistant")
        container = QWidget()
        layout = QVBoxLayout(container)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("First name Surname")
        layout.addWidget(QLabel("Child first name and surname"))
        layout.addWidget(self.name_input)
        folder_row = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        folder_row.addWidget(self.folder_label)
        browse = QPushButton("Choose DOCX folder")
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        self.profile_label = QLabel()
        self.profile_label.setWordWrap(True)
        layout.addWidget(self.profile_label)
        button_row = QHBoxLayout()
        self.process_button = QPushButton("Process")
        self.process_button.clicked.connect(self.process)
        button_row.addWidget(self.process_button)
        self.preview_button = QPushButton("Preview DOCX locally")
        self.preview_button.clicked.connect(self.preview_document)
        button_row.addWidget(self.preview_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)
        self.continue_button = QPushButton("Continue after login")
        self.continue_button.clicked.connect(self.continue_after_login)
        self.continue_button.setEnabled(False)
        button_row.addWidget(self.continue_button)
        layout.addLayout(button_row)
        self.summary = QLabel("No document processed")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.submit_button = QPushButton("Submit verified form")
        self.submit_button.clicked.connect(self.submit)
        self.submit_button.setEnabled(False)
        layout.addWidget(self.submit_button)
        self.status_panel = QTextEdit()
        self.status_panel.setReadOnly(True)
        layout.addWidget(self.status_panel)
        self.setCentralWidget(container)
        self.resize(720, 480)
        self.refresh_settings()

    def refresh_settings(self) -> None:
        try:
            settings = load_settings(self.settings_path)
            self.folder_label.setText(f"DOCX folder: {settings.docx_folder}")
            self.profile_label.setText(f"Browser: {settings.browser} | local profile: {settings.browser_profile} | dry run: {settings.dry_run}")
        except WorkflowError as exc:
            self.status_panel.append(str(exc))

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose DOCX folder")
        if not folder:
            return
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        data["docx_folder"] = folder
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.settings_path)
        self.refresh_settings()

    def process(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.summary.setText("Processing")
        self.status_panel.clear()
        self.submit_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.worker = Worker(self.settings_path, self.name_input.text())
        self.worker.status.connect(self.status_panel.append)
        self.worker.authentication_needed.connect(self.authentication_needed)
        self.worker.review_ready.connect(self.review_ready)
        self.worker.outcome.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.worker.start()
        self.process_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.preview_button.setEnabled(False)

    def preview_document(self) -> None:
        try:
            settings = load_settings(self.settings_path)
            child = parse_child_name(self.name_input.text())
            path = find_document(settings.docx_folder, child, settings.filename_patterns)
            parsed = parse_document(path)
            self.summary.setText(f"Local preview only — nothing sent or submitted\nChild: {child.display}\nDOCX: {path.name}\nLabels parsed: {len(parsed.fields)}")
            self.status_panel.append("DOCX parsed locally. Configure real site selectors and field mapping before Process can fill a form.")
        except WorkflowError as exc:
            self.summary.setText("Local preview stopped")
            self.status_panel.append(str(exc))

    def authentication_needed(self) -> None:
        self.status_panel.append("Sign in manually in the browser, then press Continue after login")
        self.continue_button.setEnabled(True)

    def continue_after_login(self) -> None:
        self.continue_button.setEnabled(False)
        if self.worker:
            self.worker.continue_event.set()

    def review_ready(self, summary: ReviewSummary) -> None:
        self.summary.setText(f"Child: {summary.child_name}\nDOCX: {summary.document_name}\nPopulated: {summary.populated}\nVerified: {summary.verified}\nWarnings: {len(summary.warnings)}")
        settings = load_settings(self.settings_path)
        self.submit_button.setEnabled(not settings.dry_run and settings.review_before_submit)

    def submit(self) -> None:
        self.submit_button.setEnabled(False)
        if self.worker:
            self.worker.submit_event.set()

    def stop(self) -> None:
        if self.worker:
            self.worker.stop()
        self.status_panel.append("Stopping…")

    def finished(self, message: str) -> None:
        self.status_panel.append(message)
        self.process_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.submit_button.setEnabled(False)

    def failed(self, message: str) -> None:
        self.summary.setText("STOPPED — no confirmed submission")
        self.status_panel.append(message)
        self.process_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.submit_button.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(15000)
            if self.worker.isRunning():
                event.ignore()
                return
        event.accept()
