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

    counts = {"submit": 0}

    class FakeBrowser:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def open_site(self):
            return object()

        def verify_domain(self):
            pass

    class FakeSite:
        def __init__(self, *_):
            pass

        def authenticated(self):
            return True

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
    monkeypatch.setattr(workflow_module, "require_selectors", lambda selectors: None)

    def settings(dry_run: bool):
        data = json.loads(Path("config/settings.example.json").read_text(encoding="utf-8"))
        data.update(docx_folder=str(docx_dir), mapping_file=str(mapping_path), dry_run=dry_run)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return load_settings(path)

    statuses = []
    dry = Workflow(settings(True), statuses.append, lambda: None, lambda summary: None,
                   Event(), Event(), Event())
    assert dry.run("Іван Шевченко") == "DRY RUN COMPLETE — nothing submitted"
    assert dry.machine.current is State.READY_TO_SUBMIT
    assert counts["submit"] == 0

    stop = Event()
    manual = Workflow(settings(False), statuses.append, lambda: None, lambda summary: stop.set(),
                      stop, Event(), Event())
    with pytest.raises(Stopped):
        manual.run("Іван Шевченко")
    assert manual.machine.current is State.ERROR
    assert counts["submit"] == 0
