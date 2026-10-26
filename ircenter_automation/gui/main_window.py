import json
import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from ..documents import inspect_document, parse_document
from ..document_source import drive_folder_id, open_document
from .. import __version__
from ..errors import WorkflowError
from ..extension_workflow import ExtensionWorkflow
from ..manual_entry import prepare_manual_entry
from ..school_ipr_2026 import extract_portal_fields
from ..normalization import comparison_key, parse_child_name, resolve_two_word_name
from ..settings import load_settings
from ..updater import Release, UpdateError, check_for_update, download_update, launch_update
from ..workflow import ReviewSummary, Workflow


class Worker(QThread):
    status = Signal(str)
    authentication_needed = Signal()
    review_ready = Signal(object)
    outcome = Signal(str)
    failed = Signal(str)

    def __init__(self, settings_path: Path, name: str, class_name: str = ""):
        super().__init__()
        self.settings_path = settings_path
        self.name = name
        self.class_name = class_name
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
            self.outcome.emit(workflow.run(self.name, self.class_name))
        except WorkflowError as exc:
            self.failed.emit(str(exc))
        except Exception:
            # Browser/library exceptions may contain page contents; never display or log them.
            self.failed.emit("Unexpected browser or application error. Nothing will be submitted automatically; inspect the site manually.")

    def stop(self) -> None:
        self.stop_event.set()
        self.continue_event.set()
        self.submit_event.set()


class UpdateCheckWorker(QThread):
    found = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.found.emit(check_for_update())
        except UpdateError as exc:
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, release: Release, destination: Path):
        super().__init__()
        self.release = release
        self.destination = destination

    def run(self) -> None:
        try:
            self.ready.emit(download_update(self.release, self.destination))
        except UpdateError as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, settings_path: Path):
        super().__init__()
        self.settings_path = settings_path
        self.worker: Worker | None = None
        self.packaged = bool(getattr(sys, "frozen", False) and sys.platform == "win32")
        self.available_release: Release | None = None
        self.update_check: UpdateCheckWorker | None = None
        self.update_download: UpdateDownloadWorker | None = None
        self.manual_update_check = False
        self.setWindowTitle(f"IR Center — DOCX form assistant v{__version__}")
        container = QWidget()
        layout = QVBoxLayout(container)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name Surname or Surname Name")
        layout.addWidget(QLabel("Child's first name and surname, in either order for school IPR DOCX"))
        layout.addWidget(self.name_input)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Document source:"))
        self.source_mode = QComboBox()
        self.source_mode.addItem("Local folder", "local")
        self.source_mode.addItem("Google Drive", "drive")
        self.source_mode.currentIndexChanged.connect(self.choose_source_mode)
        source_row.addWidget(self.source_mode)
        layout.addLayout(source_row)
        self.folder_container = QWidget()
        folder_row = QHBoxLayout(self.folder_container)
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        folder_row.addWidget(self.folder_label)
        self.folder_button = QPushButton("Choose DOCX folder")
        self.folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_button)
        layout.addWidget(self.folder_container)
        self.drive_container = QWidget()
        drive_layout = QVBoxLayout(self.drive_container)
        link_row = QHBoxLayout()
        self.drive_link_input = QLineEdit()
        self.drive_link_input.setPlaceholderText("Google Drive parent folder link")
        link_row.addWidget(self.drive_link_input)
        self.drive_link_button = QPushButton("Save Drive link")
        self.drive_link_button.clicked.connect(self.save_drive_link)
        link_row.addWidget(self.drive_link_button)
        drive_layout.addLayout(link_row)
        class_row = QHBoxLayout()
        class_row.addWidget(QLabel("Class folder:"))
        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText("7-A")
        class_row.addWidget(self.class_input)
        drive_layout.addLayout(class_row)
        layout.addWidget(self.drive_container)
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
        self.update_button = QPushButton("Check for updates")
        self.update_button.clicked.connect(self.update_clicked)
        self.update_button.setVisible(self.packaged)
        layout.addWidget(self.update_button)
        self.profile_label = QLabel()
        self.profile_label.setWordWrap(True)
        layout.addWidget(self.profile_label)
        button_row = QHBoxLayout()
        self.process_button = QPushButton("Process")
        self.process_button.clicked.connect(self.process)
        button_row.addWidget(self.process_button)
        self.preview_button = QPushButton("Preview DOCX")
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
        if self.packaged:
            QTimer.singleShot(1500, self.check_updates)

    def check_updates(self, manual: bool = False) -> None:
        if not self.packaged or (self.update_check and self.update_check.isRunning()):
            return
        self.manual_update_check = manual
        self.update_button.setEnabled(False)
        self.update_check = UpdateCheckWorker()
        self.update_check.found.connect(self.update_found)
        self.update_check.failed.connect(self.update_check_failed)
        self.update_check.start()

    def update_found(self, release: Release | None) -> None:
        self.available_release = release
        if release:
            self.update_button.setText(f"Install update v{release.version}")
            self.status_panel.append(f"Update v{release.version} is available.")
        elif self.manual_update_check:
            self.status_panel.append("The app is up to date.")
        self.update_button.setEnabled(not (self.worker and self.worker.isRunning()))

    def update_check_failed(self, message: str) -> None:
        if self.manual_update_check:
            self.status_panel.append(message)
        self.update_button.setEnabled(not (self.worker and self.worker.isRunning()))

    def update_clicked(self) -> None:
        if self.available_release is None:
            self.check_updates(manual=True)
            return
        if self.worker and self.worker.isRunning():
            self.status_panel.append("Finish or stop the current document before updating.")
            return
        self.update_button.setEnabled(False)
        self.status_panel.append("Downloading and verifying the update installer…")
        self.update_download = UpdateDownloadWorker(
            self.available_release, self.settings_path.parent / "updates",
        )
        self.update_download.ready.connect(self.update_downloaded)
        self.update_download.failed.connect(self.update_download_failed)
        self.update_download.start()

    def update_downloaded(self, installer: Path) -> None:
        # The signal is queued to the GUI thread while run() may still be returning.
        # Let the worker finish before QApplication tears down its QThread object.
        if self.update_download:
            self.update_download.wait(1000)
        try:
            launch_update(installer)
        except UpdateError as exc:
            self.update_download_failed(str(exc))
            return
        self.status_panel.append("Installer started. The app will close and reopen after updating.")
        QApplication.instance().quit()

    def update_download_failed(self, message: str) -> None:
        self.status_panel.append(message)
        self.update_button.setEnabled(True)

    def refresh_settings(self) -> None:
        try:
            settings = load_settings(self.settings_path)
            self.folder_label.setText(f"DOCX folder: {settings.docx_folder}")
            self.source_mode.blockSignals(True)
            self.source_mode.setCurrentIndex(self.source_mode.findData(settings.document_source))
            self.source_mode.blockSignals(False)
            self.folder_container.setVisible(settings.document_source == "local")
            self.drive_container.setVisible(settings.document_source == "drive")
            self.drive_link_input.setText(settings.drive_folder_url)
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

    def choose_source_mode(self) -> None:
        selection = self.source_mode.currentData()
        if selection is None or (self.worker and self.worker.isRunning()):
            return
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        data["document_source"] = selection
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.settings_path)
        self.refresh_settings()

    def save_drive_link(self) -> bool:
        link = self.drive_link_input.text().strip()
        try:
            if link:
                drive_folder_id(link)
        except ValueError as exc:
            self.status_panel.append(str(exc))
            return False
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        data["drive_folder_url"] = link
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.settings_path)
        self.refresh_settings()
        self.status_panel.append("Google Drive parent folder link saved.")
        return True

    def _ready_settings(self):
        settings = load_settings(self.settings_path)
        if settings.document_source == "drive":
            if self.drive_link_input.text().strip() != settings.drive_folder_url:
                if not self.save_drive_link():
                    raise WorkflowError("Google Drive folder link is invalid")
                settings = load_settings(self.settings_path)
            if not settings.drive_folder_url:
                raise WorkflowError("Paste and save the Google Drive parent folder link")
            if not self.class_input.text().strip():
                raise WorkflowError("Enter the class folder name, such as 7-A")
        return settings

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
        try:
            self._ready_settings()
        except WorkflowError as exc:
            self.status_panel.append(str(exc))
            return
        self.summary.setText("Processing")
        self.status_panel.clear()
        self.submit_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.worker = Worker(self.settings_path, self.name_input.text(), self.class_input.text())
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
        self.source_mode.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.drive_link_input.setEnabled(False)
        self.drive_link_button.setEnabled(False)
        self.class_input.setEnabled(False)
        self.pair_button.setEnabled(False)
        self.update_button.setEnabled(False)

    def show_manual_entry(self) -> None:
        try:
            guide = prepare_manual_entry(self._ready_settings(), self.name_input.text(), self.class_input.text())
        except WorkflowError as exc:
            self.summary.setText("Manual guide stopped")
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
            settings = self._ready_settings()
            child = parse_child_name(self.name_input.text())
            with open_document(settings, child, self.class_input.text()) as source:
                layout = inspect_document(source.path)
                parsed = parse_document(source.path)
                if layout.startswith("11-section school IPR"):
                    child = resolve_two_word_name(child, parsed.fields[comparison_key("docx_child_full_name")])
                    base = {name: parsed.fields[comparison_key(name)] for name in
                            ("execution_period", "year_of_study", "child_grade", "parents_phones")}
                    candidates = extract_portal_fields(source.path, base)
                    self.summary.setText(f"Preview only — nothing sent or submitted\nChild: {child.display}\nDOCX: {source.name}\nLayout: {layout}\nMatching populated controls: {len(candidates)}")
                    self.status_panel.append("Matching fields can be filled in Chrome. Review the complete form before generating the document.")
                    return
            self.summary.setText(f"Preview only — nothing sent or submitted\nChild: {child.display}\nDOCX: {source.name}\nLabels parsed: {len(parsed.fields)}")
            self.status_panel.append("DOCX parsed locally. Configure real site selectors and field mapping before Process can fill a form.")
        except WorkflowError as exc:
            self.summary.setText("Preview stopped")
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
        self.source_mode.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.drive_link_input.setEnabled(True)
        self.drive_link_button.setEnabled(True)
        self.class_input.setEnabled(True)
        self.pair_button.setEnabled(True)
        self.update_button.setEnabled(True)
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
        self.source_mode.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.drive_link_input.setEnabled(True)
        self.drive_link_button.setEnabled(True)
        self.class_input.setEnabled(True)
        self.pair_button.setEnabled(True)
        self.update_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.submit_button.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.update_download and self.update_download.isRunning():
            self.status_panel.append("Wait for the update download to finish before closing.")
            event.ignore()
            return
        if self.update_check and self.update_check.isRunning():
            self.update_check.wait(13000)
            if self.update_check.isRunning():
                event.ignore()
                return
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(15000)
            if self.worker.isRunning():
                event.ignore()
                return
        event.accept()
