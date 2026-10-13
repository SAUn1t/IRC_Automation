import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from ..documents import find_document, inspect_document, parse_document
from ..errors import WorkflowError
from ..extension_workflow import ExtensionWorkflow
from ..manual_entry import prepare_manual_entry
from ..normalization import comparison_key, parse_child_name, resolve_two_word_name
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
            settings = load_settings(self.settings_path)
            if settings.browser_transport == "extension":
                workflow = ExtensionWorkflow(
                    settings, self.status.emit, self.review_ready.emit, self.stop_event,
                )
            else:
                workflow = Workflow(settings, self.status.emit,
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
        self.name_input.setPlaceholderText("Name Surname or Surname Name")
        layout.addWidget(QLabel("Child's first name and surname, in either order for school IPR DOCX"))
        layout.addWidget(self.name_input)
        folder_row = QHBoxLayout()
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        folder_row.addWidget(self.folder_label)
        browse = QPushButton("Choose DOCX folder")
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        browser_row = QHBoxLayout()
        browser_row.addWidget(QLabel("Browser mode:"))
        self.browser_mode = QComboBox()
        self.browser_mode.addItem("Chrome extension (existing profile)", ("chrome", "extension"))
        self.browser_mode.addItem("Chrome normal window", ("chrome", "cdp"))
        self.browser_mode.addItem("Edge normal window", ("msedge", "cdp"))
        self.browser_mode.addItem("Playwright Chromium", ("chromium", "playwright"))
        self.browser_mode.addItem("Playwright Chrome", ("chrome", "playwright"))
        self.browser_mode.addItem("Playwright Edge", ("msedge", "playwright"))
        self.browser_mode.currentIndexChanged.connect(self.choose_browser_mode)
        browser_row.addWidget(self.browser_mode)
        layout.addLayout(browser_row)
        self.pair_button = QPushButton("Copy extension pairing code")
        self.pair_button.clicked.connect(self.copy_extension_pairing_code)
        layout.addWidget(self.pair_button)
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
        self.manual_button = QPushButton("Copy fields for normal browser")
        self.manual_button.clicked.connect(self.show_manual_entry)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)
        self.continue_button = QPushButton("Continue after login")
        self.continue_button.clicked.connect(self.continue_after_login)
        self.continue_button.setEnabled(False)
        button_row.addWidget(self.continue_button)
        layout.addLayout(button_row)
        layout.addWidget(self.manual_button)
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
            mode = next(
                (index for index in range(self.browser_mode.count())
                 if self.browser_mode.itemData(index) == (settings.browser, settings.browser_transport)), -1
            )
            self.browser_mode.blockSignals(True)
            self.browser_mode.setCurrentIndex(mode)
            self.browser_mode.blockSignals(False)
            self.profile_label.setText(
                f"Browser: {settings.browser} ({settings.browser_transport}) | "
                f"local profile: {settings.browser_profile} | dry run: {settings.dry_run}"
            )
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

    def choose_browser_mode(self) -> None:
        selection = self.browser_mode.currentData()
        if selection is None or (self.worker and self.worker.isRunning()):
            return
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        data["browser"], data["browser_transport"] = selection
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.settings_path)
        self.refresh_settings()

    def copy_extension_pairing_code(self) -> None:
        settings = load_settings(self.settings_path)
        if not settings.extension_token:
            self.status_panel.append("Pairing code is missing; restart the app")
            return
        QApplication.clipboard().setText(settings.extension_token)
        self.status_panel.append("Pairing code copied. Paste it into the Chrome extension popup and save.")

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
        self.manual_button.setEnabled(False)
        self.browser_mode.setEnabled(False)
        self.pair_button.setEnabled(False)

    def show_manual_entry(self) -> None:
        try:
            guide = prepare_manual_entry(load_settings(self.settings_path), self.name_input.text())
        except WorkflowError as exc:
            self.summary.setText("Local manual guide stopped")
            self.status_panel.append(str(exc))
            return
        self.summary.setText(
            f"Manual copy guide — nothing sent or submitted\nChild: {guide.child_name}\nDOCX: {guide.document_name}"
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Copy four IPR fields")
        layout = QVBoxLayout(dialog)
        note = QLabel(
            "Open the matching child's Створити ІПР form in your normal browser. "
            "Copy each value into the named field, then review the whole form before Сформувати документ."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        for field in guide.fields:
            layout.addWidget(QLabel(f"{field.label} — {field.portal_name}"))
            row = QHBoxLayout()
            value = QLineEdit(field.value)
            value.setReadOnly(True)
            row.addWidget(value)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _checked=False, text=field.value: QApplication.clipboard().setText(text))
            row.addWidget(copy)
            layout.addLayout(row)
        dialog.resize(650, 330)
        dialog.exec()

    def preview_document(self) -> None:
        try:
            settings = load_settings(self.settings_path)
            child = parse_child_name(self.name_input.text())
            path = find_document(settings.docx_folder, child, settings.filename_patterns)
            layout = inspect_document(path)
            parsed = parse_document(path)
            if layout.startswith("11-section school IPR"):
                child = resolve_two_word_name(child, parsed.fields[comparison_key("docx_child_full_name")])
                self.summary.setText(f"Local preview only — nothing sent or submitted\nChild: {child.display}\nDOCX: {path.name}\nLayout: {layout}\nExact scalar candidates: {len(parsed.fields) - 1}")
                self.status_panel.append("Only exact scalar fields can be transferred automatically. All remaining IPR sections need manual review.")
                return
            self.summary.setText(f"Local preview only — nothing sent or submitted\nChild: {child.display}\nDOCX: {path.name}\nLabels parsed: {len(parsed.fields)}")
            self.status_panel.append("DOCX parsed locally. Configure real site selectors and field mapping before Process can fill a form.")
        except WorkflowError as exc:
            self.summary.setText("Local preview stopped")
            self.status_panel.append(str(exc))

    def authentication_needed(self) -> None:
        self.status_panel.append(
            "Complete any portal security verification and sign in in the open browser. "
            "Open Журнал висновків; press Continue only when the journal is visible."
        )
        self.continue_button.setEnabled(True)

    def continue_after_login(self) -> None:
        self.continue_button.setEnabled(False)
        if self.worker:
            self.worker.continue_event.set()

    def review_ready(self, summary: ReviewSummary) -> None:
        warning_text = "\n".join(summary.warnings)
        self.summary.setText(f"Child: {summary.child_name}\nDOCX: {summary.document_name}\nPopulated: {summary.populated}\nVerified: {summary.verified}\n{warning_text}")
        settings = load_settings(self.settings_path)
        self.submit_button.setEnabled(
            settings.browser_transport != "extension" and not settings.manual_review_only
            and not settings.dry_run and settings.review_before_submit
        )

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
        self.manual_button.setEnabled(True)
        self.browser_mode.setEnabled(True)
        self.pair_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.submit_button.setEnabled(False)

    def failed(self, message: str) -> None:
        self.summary.setText("STOPPED — no confirmed submission")
        self.status_panel.append(message)
        self.process_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.manual_button.setEnabled(True)
        self.browser_mode.setEnabled(True)
        self.pair_button.setEnabled(True)
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
