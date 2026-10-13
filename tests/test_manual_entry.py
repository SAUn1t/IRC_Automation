import json
from pathlib import Path

import pytest
from docx import Document

from ircenter_automation.errors import ChildIdentityMismatch
from ircenter_automation.manual_entry import prepare_manual_entry
from ircenter_automation.settings import load_settings


def test_manual_guide_uses_only_confirmed_school_ipr_fields(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = Document()
    for line in (
        "1. Період виконання з 01.09.2026 по 31.05.2027",
        "прізвище, власне ім’я, по батькові(за наявності) Шевченко Іван Петрович",
        "контактні номери телефонів батьків (інших законних представників) учня 000 000 000",
        "клас навчання 2-А", "рік навчання 2",
        "5. Створення інклюзивного освітнього середовища, зокрема:",
        "11. Погодження індивідуальної програми розвитку з батьками",
    ):
        doc.add_paragraph(line)
    doc.save(docs / "Шевченко Іван.docx")
    data = json.loads(Path("config/settings.example.json").read_text(encoding="utf-8"))
    data["docx_folder"] = str(docs)
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(data), encoding="utf-8")
    settings = load_settings(settings_path)

    guide = prepare_manual_entry(settings, "Шевченко Іван")
    assert guide.child_name == "Іван Шевченко"
    assert guide.document_name == "Шевченко Іван.docx"
    assert [(field.portal_name, field.value) for field in guide.fields] == [
        ("execution_period", "з 01.09.2026 по 31.05.2027"),
        ("year_of_study", "2"),
        ("child_grade", "2-А"),
        ("parents_phones", "000 000 000"),
    ]
    doc.save(docs / "Петренко Іван.docx")
    with pytest.raises(ChildIdentityMismatch):
        prepare_manual_entry(settings, "Іван Петренко")
