from pathlib import Path

import pytest
from docx import Document

from ircenter_automation.documents import find_document, parse_document
from ircenter_automation.errors import (
    DocumentNotFound, DocumentParsingError, MultipleDocumentsFound, WorkflowError,
)
from ircenter_automation.mapping import FieldSpec, map_document
from ircenter_automation.normalization import comparison_key, parse_child_name
from ircenter_automation.state import State, StateMachine


def test_unicode_name_normalization_and_exactness():
    child = parse_child_name("  Іва́н   О’Коннор-Шевченко  ")
    assert child.display == "Іва́н О’Коннор-Шевченко"
    assert child.matches("ІВА́Н", "О’КОННОР-ШЕВЧЕНКО")
    assert not child.matches("Іван", "О’Коннор-Шевченко")
    assert not child.matches("Іва́н", "О'Коннор-Шевченко")
    with pytest.raises(WorkflowError):
        parse_child_name("Іван Іванович Шевченко")


def test_document_discovery_stops_on_missing_or_multiple(tmp_path: Path):
    child = parse_child_name("Іван Шевченко")
    patterns = ("{Surname} {Name}.docx", "{Name} {Surname}.docx")
    with pytest.raises(DocumentNotFound):
        find_document(tmp_path, child, patterns)
    first = tmp_path / "Шевченко Іван.docx"
    first.touch()
    assert find_document(tmp_path, child, patterns) == first
    (tmp_path / "Іван Шевченко.docx").touch()
    with pytest.raises(MultipleDocumentsFound):
        find_document(tmp_path, child, patterns)


def test_docx_paragraph_table_empty_and_multiline(tmp_path: Path):
    path = tmp_path / "sample.docx"
    doc = Document()
    doc.add_heading("Анкета", 1)
    doc.add_paragraph("Дата народження: 01.02.2015")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Примітки"
    table.cell(0, 1).text = "Рядок 1\nРядок 2"
    table.cell(1, 0).text = "Згода"
    table.cell(1, 1).text = "☐"
    doc.save(path)
    parsed = parse_document(path)
    assert parsed.headings == ("Анкета",)
    assert parsed.fields[comparison_key("Примітки")] == "Рядок 1\nРядок 2"
    assert parsed.fields[comparison_key("Згода")] == "no"


def test_docx_duplicate_and_malformed_stop(tmp_path: Path):
    path = tmp_path / "duplicate.docx"
    doc = Document()
    doc.add_paragraph("Вік: 9")
    doc.add_paragraph("Вік: 10")
    doc.save(path)
    with pytest.raises(DocumentParsingError):
        parse_document(path)
    corrupt = tmp_path / "corrupt.docx"
    corrupt.write_bytes(b"not a Word document")
    with pytest.raises(DocumentParsingError):
        parse_document(corrupt)


def test_mapping_missing_required_and_invalid_date():
    spec = FieldSpec("birth", "Дата народження", "#birth", "date", True, {}, None, None, "input")
    with pytest.raises(DocumentParsingError):
        map_document({}, (spec,))
    with pytest.raises(DocumentParsingError):
        map_document({comparison_key(spec.docx_label): "31.02.2020"}, (spec,))
    result = map_document({comparison_key(spec.docx_label): "01.02.2020"}, (spec,))
    assert result[0].expected == "2020-02-01"


def test_state_machine_rejects_skipped_confirmation():
    machine = StateMachine()
    machine.advance(State.INPUT_VALIDATED)
    with pytest.raises(ValueError):
        machine.advance(State.FORM_POPULATED)
    machine.advance(State.ERROR)
    with pytest.raises(ValueError):
        machine.advance(State.DOCUMENT_FOUND)
