from pathlib import Path
from threading import Event

import ircenter_automation.extension_workflow as module
from ircenter_automation.manual_entry import ManualEntryGuide, ManualField
from ircenter_automation.school_ipr_2026 import PortalField
from ircenter_automation.settings import load_settings


def test_extension_workflow_waits_for_installed_extension_and_stops_for_review(monkeypatch):
    settings = load_settings(Path("config/settings.example.json"))
    guide = ManualEntryGuide("Іван Шевченко", "synthetic.docx", (
        ManualField("Період виконання", "execution_period", "з 01.09.2026 по 31.05.2027"),
        ManualField("Рік навчання", "year_of_study", "2"),
        ManualField("Клас навчання", "child_grade", "2-А"),
        ManualField("Телефони батьків", "parents_phones", "000 000 000"),
    ))
    monkeypatch.setattr(module, "prepare_manual_entry", lambda *_: guide)
    class FakeBridge:
        def __init__(self, _token, _guide):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def next_status(self):
            return "ready", "Four fields filled and read back"

    monkeypatch.setattr(module, "ExtensionBridge", FakeBridge)
    statuses = []
    reviews = []
    result = module.ExtensionWorkflow(settings, statuses.append, reviews.append, Event()).run("Шевченко Іван")
    assert any("signed-in Chrome profile" in status for status in statuses)
    assert result.startswith("MANUAL REVIEW")
    assert reviews[0].child_name == "Іван Шевченко"
    assert reviews[0].verified == 4


def test_extension_review_mentions_skipped_section9(monkeypatch):
    settings = load_settings(Path("config/settings.example.json"))
    guide = ManualEntryGuide("Іван Шевченко", "synthetic.docx", (), (
        PortalField("execution_period", "з 01.09.2026 по 31.05.2027", "text"),
        PortalField("5[29][2]", "Адаптація", "select"),
    ))
    monkeypatch.setattr(module, "prepare_manual_entry", lambda *_: guide)

    class FakeBridge:
        def __init__(self, _token, _guide):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def next_status(self):
            return "ready", "Ready"

    monkeypatch.setattr(module, "ExtensionBridge", FakeBridge)
    reviews = []
    module.ExtensionWorkflow(settings, lambda _: None, reviews.append, Event()).run("Шевченко Іван")
    assert any("Section 9 was skipped" in warning for warning in reviews[0].warnings)
    assert any("Review subject adaptation details" in warning for warning in reviews[0].warnings)
