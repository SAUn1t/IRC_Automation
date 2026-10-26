"""Anonymized examples of the current teacher DOCX layout."""

from pathlib import Path

import pytest
from docx import Document

from ircenter_automation.school_ipr_2026 import extract_portal_fields


@pytest.mark.parametrize("section9_choices", [
    (" Так", " Ні"),
    ("+ Так", " Ні"),
    (" Так", "+ Ні"),
])
def test_extracts_matching_sections_and_skips_section9(tmp_path: Path, section9_choices):
    doc = Document()
    for text in (
        "3. Категорії (типи) особливих освітніх потреб: мовленнєві труднощі",
        "4. Рівень підтримки (протокол засідання від 12 жовтня 2026 р. № 7):",
        " перший рівень підтримки", "+ другий рівень підтримки",
        " третій рівень підтримки", " четвертий рівень підтримки",
        " п’ятий рівень підтримки",
        "5. Створення інклюзивного освітнього середовища",
        "наявність індивідуального навчального плану:", " так", "+ ні",
        "здійснення освітнього процесу:", "+ за розкладом класу", " за адаптованим розкладом",
        "забезпечення допоміжними засобами для навчання:", " так", "+ ні",
        "8. Особливості процесу оцінювання:",
        "+ спрощення інструкцій", "+ гнучкість використання часу",
        "+ зменшення кількості завдань", "+ використання оптимальних форм оцінювання",
        "+ використання доступних форм викладу інформації", "+ використання допоміжних засобів",
        " уникнення графічних завдань", " уникнення зорових/слухових подразників",
        " інше __________________",
        "9. Потреба у продовженні строків навчання:", *section9_choices,
        "прізвище, власне ім’я, по батькові (за наявності) батьків (інших законних представників) учня Шевченко Олена Іванівна",
        "Я, Шевченко Олена Іванівна,",
    ):
        doc.add_paragraph(text)
    subjects = doc.add_table(rows=1, cols=3)
    subjects.rows[0].cells[0].text = "Найменування навчального предмета"
    for name in ("Математика", "Читання"):
        cells = subjects.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = name, "Адаптація", "Учитель Приклад"
    goals = doc.add_table(rows=1, cols=5)
    goals.rows[0].cells[0].text = "Освітня галузь/ навчальний предмет"
    cells = goals.add_row().cells
    for cell, value in zip(cells, ("Мовна", "Читає", "Читати", "Прочитає", "")):
        cell.text = value
    path = tmp_path / "example.docx"
    doc.save(path)
    base = {"execution_period": "з 01.09.2026 по 31.05.2027", "year_of_study": "2",
            "child_grade": "2-А", "parents_phones": "000 000 000"}
    result = {field.name: field.value for field in extract_portal_fields(path, base)}
    assert result["3[1][1]"] == "мовленнєві труднощі"
    assert result["supportLevel"] == "2"
    assert result["5[26][1]"] == "0"
    assert result["5[27][1]"] == "за розкладом класу"
    assert result["5[29][1]"] == "Математика"
    assert result["5[30][1]"] == "Читання"
    assert result["6[1][4]"] == "Прочитає"
    assert result["8[7][1]"] == "false"
    assert result["8[9][0]"] == "false"
    assert "9[1][1]" not in result
    assert result["footer_parents_names"] == "Шевченко Олена Іванівна"


@pytest.mark.parametrize("markers, expected", [
    (("+ ",) * 5 + ("• ",) * 3, ["true"] * 5 + ["false"] * 3),
    (("+ ",) * 5 + ("",) * 3, ["true"] * 5 + ["false"] * 3),
    (("+ • ", "• + ", "+ • ", "• ", "• ", "•+ ", "• ", "• "),
     ["true"] * 3 + ["false"] * 2 + ["true"] + ["false"] * 2),
])
def test_assessment_bullets_and_mixed_plus_markers(tmp_path: Path, markers, expected):
    doc = Document()
    doc.add_paragraph("8. Особливості процесу оцінювання:")
    labels = (
        "спрощення інструкцій", "гнучкість використання часу",
        "зменшення кількості завдань", "використання оптимальних форм оцінювання",
        "використання доступних форм викладу інформації",
        "використання допоміжних засобів", "уникнення графічних завдань",
        "уникнення зорових/слухових подразників",
    )
    for marker, label in zip(markers, labels):
        doc.add_paragraph(marker + label)
    doc.add_paragraph("• інше __________________")
    doc.add_paragraph("9. Потреба у продовженні строків навчання:")
    path = tmp_path / "assessment.docx"
    doc.save(path)
    base = {"execution_period": "з 01.09.2026 по 31.05.2027", "year_of_study": "2",
            "child_grade": "2-А", "parents_phones": "000 000 000"}
    result = {field.name: field.value for field in extract_portal_fields(path, base)}
    assert [result[f"8[{index}][1]"] for index in range(1, 9)] == expected
    assert result["8[9][0]"] == "false"
