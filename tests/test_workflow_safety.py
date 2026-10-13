import json
from pathlib import Path
from threading import Event

import pytest
from docx import Document

import ircenter_automation.workflow as workflow_module
from ircenter_automation.errors import Stopped
from ircenter_automation.settings import load_settings
from ircenter_automation.state import State
from ircenter_automation.workflow import Workflow


def test_dry_run_and_manual_review_never_submit_without_click(tmp_path: Path, monkeypatch):
    docx_dir = tmp_path / "docs"
    docx_dir.mkdir()
    doc = Document()
    doc.add_paragraph("Дата народження: 01.02.2015")
    doc.save(docx_dir / "Шевченко Іван.docx")
    mapping_path = tmp_path / "fields.json"
    mapping_path.write_text(json.dumps({"fields": [{
        "key": "birth", "docx_label": "Дата народження", "selector": "#birth", "control": "date"
    }]}), encoding="utf-8")

    counts = {"submit": 0, "open_site": 0, "auth_checks": 0}

    class FakeBrowser:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def open_site(self):
            counts["open_site"] += 1
            return object()

        def verify_domain(self):
            pass

    class FakeSite:
        def __init__(self, *_):
            pass

        def authenticated(self):
            counts["auth_checks"] += 1
            return counts["auth_checks"] > 2

        def find_child(self, child):
            pass

        def verify_child_identity(self, child, *, on_form=False):
            pass

        def open_new_form(self):
            pass

        def verify_form_open(self, child):
            pass

        def check_validation_errors(self):
            pass

        def submit_once(self):
            counts["submit"] += 1

        def verify_submission(self):
            pass

    class FakeFiller:
        def __init__(self, page):
            pass

        def fill(self, field):
            pass

        def verify_all(self, fields):
            return {field.spec.key: True for field in fields}

    monkeypatch.setattr(workflow_module, "BrowserSession", FakeBrowser)
    monkeypatch.setattr(workflow_module, "IRCenter", FakeSite)
    monkeypatch.setattr(workflow_module, "FormFiller", FakeFiller)
    monkeypatch.setattr(workflow_module, "require_selectors", lambda selectors, manual_review_only=False: None)

    def settings(dry_run: bool, manual_review_only: bool = False):
        data = json.loads(Path("config/settings.example.json").read_text(encoding="utf-8"))
        data.update(docx_folder=str(docx_dir), mapping_file=str(mapping_path), dry_run=dry_run,
                    manual_review_only=manual_review_only)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return load_settings(path)

    statuses = []
    continue_event = Event()
    prompts = []
    def continue_after_journal():
        prompts.append(True)
        continue_event.set()

    dry = Workflow(settings(True), statuses.append, continue_after_journal, lambda summary: None,
                   Event(), continue_event, Event())
    assert dry.run("Іван Шевченко") == "DRY RUN COMPLETE — nothing submitted"
    assert dry.machine.current is State.READY_TO_SUBMIT
    assert counts["submit"] == 0
    assert len(prompts) == 2
    assert counts["open_site"] == 1
    assert any("journal is not visible yet" in status for status in statuses)

    stop = Event()
    manual = Workflow(settings(False), statuses.append, lambda: None, lambda summary: stop.set(),
                      stop, Event(), Event())
    with pytest.raises(Stopped):
        manual.run("Іван Шевченко")
    assert manual.machine.current is State.ERROR
    assert counts["submit"] == 0

    handoff_stop = Event()
    handoff = Workflow(settings(True, manual_review_only=True), statuses.append, lambda: None,
                       lambda summary: handoff_stop.set(), handoff_stop, Event(), Event())
    assert handoff.run("Іван Шевченко").startswith("MANUAL REVIEW ENDED")
    assert handoff.machine.current is State.MANUAL_REVIEW
    assert counts["submit"] == 0


def test_school_ipr_surname_first_input_reaches_journal_in_canonical_order(tmp_path: Path, monkeypatch):
    docx_dir = tmp_path / "docs"
    docx_dir.mkdir()
    doc = Document()
    for text in (
        "1. Період виконання з 01.09.2026 по 31.05.2027",
        "прізвище, власне ім’я, по батькові(за наявності) Шевченко Іван Петрович",
        "контактні номери телефонів батьків (інших законних представників) учня 000 000 000",
        "клас навчання 2-А", "рік навчання 2",
        "5. Створення інклюзивного освітнього середовища, зокрема:",
        "11. Погодження індивідуальної програми розвитку з батьками",
    ):
        doc.add_paragraph(text)
    doc.save(docx_dir / "Шевченко Іван.docx")
    settings_data = json.loads(Path("config/settings.example.json").read_text(encoding="utf-8"))
    settings_data.update(docx_folder=str(docx_dir), mapping_file=str(Path("config/field_mapping.example.json").resolve()))
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings_data), encoding="utf-8")

    class FakeBrowser:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def open_site(self):
            return object()

    observed = []

    class FakeSite:
        def __init__(self, *_):
            pass

        def authenticated(self):
            return True

        def find_child(self, child):
            observed.append(child.display)
            raise Stopped("Test stops before portal interaction")

    monkeypatch.setattr(workflow_module, "BrowserSession", FakeBrowser)
    monkeypatch.setattr(workflow_module, "IRCenter", FakeSite)
    monkeypatch.setattr(workflow_module, "require_selectors", lambda *_: None)
    worker = Workflow(load_settings(settings_path), lambda _: None, lambda: None, lambda _: None,
                      Event(), Event(), Event())
    with pytest.raises(Stopped):
        worker.run("Шевченко Іван")
    assert observed == ["Іван Шевченко"]
