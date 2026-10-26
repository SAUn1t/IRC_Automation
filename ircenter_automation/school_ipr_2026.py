"""Exact, local transfers from the 2026 school IPR DOCX to its matching portal form."""

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from .errors import DocumentParsingError
from .normalization import comparison_key, normalize_space


@dataclass(frozen=True)
class PortalField:
    name: str
    value: str
    kind: str
    row_label: str = ""


_ENVIRONMENT_ROWS = (
    ("Доступність", 1), ("Освітлення", 2), ("Рівень шуму", 3),
    ("Потреба в усамітненні, його періодичність і місце", 4),
    ("Інформаційні позначки", 5), ("Меблі", 6), ("Інше", 7),
    ("використання візуального розкладу", 8),
    ("використання індивідуальних позначок", 9),
    ("збільшення часу на виконання завдань", 10),
    ("збільшення обсягу допомоги", 11),
    ("чергування видів діяльності", 12),
    ("використання заохочень", 13),
    ("використання засобів концентрації уваги", 14),
    ("картки-підказки, картки-інструкції", 15),
    ("інше", 16),
    ("зміна змісту навчальних предметів", 17),
    ("зміна вимог щодо виконання завдань", 18),
    ("зміна підходів до проведення моніторингу", 19),
    ("інше", 20),
    ("Жестова мова", 21), ("Шрифт Брайля", 22),
    ("Календарна система", 23),
    ("Комунікаційна система обміну зображеннями", 24),
    ("Інше", 25),
)

_ASSESSMENT_ROWS = (
    "спрощення інструкцій", "гнучкість використання часу",
    "зменшення кількості завдань", "використання оптимальних форм оцінювання",
    "використання доступних форм викладу інформації",
    "використання допоміжних засобів", "уникнення графічних завдань",
    "уникнення зорових/слухових подразників",
)


def _selection(text: str) -> tuple[bool, str] | None:
    value = normalize_space(text)
    if value.startswith("+"):
        return True, value[1:].strip()
    if value.startswith(("\uf07f", "☐", "□")):
        return False, value[1:].strip()
    return None


def _section(paragraphs: list[str], number: int) -> list[str]:
    starts = [i for i, text in enumerate(paragraphs) if re.match(rf"^{number}\.\s", text)]
    if len(starts) != 1:
        return []
    start = starts[0]
    end = next((i for i in range(start + 1, len(paragraphs))
                if re.match(rf"^{number + 1}\.\s", paragraphs[i])), len(paragraphs))
    return paragraphs[start:end]


def _unique_suffix(paragraphs: list[str], prefix: str) -> str | None:
    matches = [text[len(prefix):].strip(" :") for text in paragraphs if text.startswith(prefix)]
    if len(matches) > 1:
        raise DocumentParsingError(f"Duplicate school IPR label: {prefix}")
    return matches[0] if matches and matches[0] else None


def extract_portal_fields(path: Path, base: dict[str, str]) -> tuple[PortalField, ...]:
    """Return only DOCX values with the same meaning in the current 11-section form."""
    doc = Document(path)
    paragraphs = [normalize_space(p.text) for p in doc.paragraphs]
    fields: list[PortalField] = []
    seen: set[str] = set()

    def add(name: str, value: str | None, kind: str = "text", row_label: str = "") -> None:
        if value is None or not value.strip():
            return
        if name in seen:
            raise DocumentParsingError(f"Duplicate portal field mapping: {name}")
        seen.add(name)
        fields.append(PortalField(name, value.strip(), kind, row_label))

    for name, kind in (("execution_period", "text"), ("year_of_study", "select"),
                       ("child_grade", "text"), ("parents_phones", "text")):
        add(name, base[name], kind)

    for name, prefix, kind in (
        ("parent_address", "адреса задекларованого/зареєстрованого місця проживання (перебування)", "textarea"),
        ("child_enrollment_date", "дата зарахування до закладу загальної середньої освіти", "text"),
    ):
        add(name, _unique_suffix(paragraphs, prefix), kind)

    section3 = _section(paragraphs, 3)
    if section3 and ":" in section3[0]:
        add("3[1][1]", section3[0].split(":", 1)[1], "textarea")

    section4 = _section(paragraphs, 4)
    if section4:
        match = re.search(r"протокол засідання від\s+(\d{1,2})\s+([а-щьюяіїєґ]+)\s+(20\d{2})\s*р\.\s*№\s*(\d+)", section4[0], re.I)
        if match:
            day, month, year, number = match.groups()
            add("protocol_date", day, "number")
            add("protocol_month", month, "text")
            add("protocol_year", year[2:], "number")
            add("protocol_number", number, "number")
        levels = [(i, selected) for i, text in enumerate(section4[1:6], 1)
                  if (selected := _selection(text)) is not None]
        if len(levels) == 5 and sum(checked for _, (checked, _) in levels) == 1:
            add("supportLevel", str(next(i for i, (checked, _) in levels if checked)), "select")

    environment = next((table for table in doc.tables if table.rows and
                        comparison_key(table.cell(0, 0).text).startswith(comparison_key("Назва адаптації/модифікації освітнього середовища"))), None)
    if environment:
        candidates = []
        for row in environment.rows[1:]:
            label = normalize_space(row.cells[0].text)
            if any(comparison_key(label).startswith(comparison_key(expected)) for expected, _ in _ENVIRONMENT_ROWS):
                candidates.append((label, normalize_space(row.cells[1].text)))
        if len(candidates) != len(_ENVIRONMENT_ROWS):
            raise DocumentParsingError("School IPR environment row layout changed")
        for (label, value), (expected, number) in zip(candidates, _ENVIRONMENT_ROWS):
            if not comparison_key(label).startswith(comparison_key(expected)):
                raise DocumentParsingError("School IPR environment row order changed")
            add(f"5[{number}][1]", value, "textarea", expected)

    section5 = _section(paragraphs, 5)
    if section5:
        def selected_after(label: str, count: int = 2) -> str | None:
            positions = [i for i, text in enumerate(section5) if text.startswith(label)]
            if len(positions) != 1:
                return None
            choices = [_selection(text) for text in section5[positions[0] + 1:positions[0] + 1 + count]]
            if any(choice is None for choice in choices) or sum(choice[0] for choice in choices) != 1:
                return None
            return next(choice[1] for choice in choices if choice[0])

        plan = selected_after("наявність індивідуального навчального плану")
        if plan and comparison_key(plan) in ("так", "ні"):
            add("5[26][1]", "1" if comparison_key(plan) == "так" else "0", "radio")
        schedule = selected_after("здійснення освітнього процесу")
        if schedule:
            add("5[27][1]", schedule.rstrip(" _"), "select")
        aids = selected_after("забезпечення допоміжними засобами для навчання")
        if aids and comparison_key(aids) in ("так", "ні"):
            add("5[28][1]", "1" if comparison_key(aids) == "так" else "0", "radio")
            if comparison_key(aids) == "так":
                add("5[28][2]", _unique_suffix(section5, "перелік допоміжних засобів для навчання, яких потребує учень"), "textarea")

    tables = (
        ("Найменування навчального предмета", "5", 29, ("textarea", "select", "textarea")),
        ("Освітня галузь/", "6", 1, ("textarea", "textarea", "textarea", "textarea", "textarea")),
        ("Найменування заняття", "7", 1, ("textarea", "textarea", "textarea", "textarea")),
        ("Прізвище, власне ім’я,", "10", 1, ("textarea", "textarea")),
    )
    for first_header, section, base_row, kinds in tables:
        matches = [table for table in doc.tables if table.rows and
                   comparison_key(table.cell(0, 0).text).startswith(comparison_key(first_header))]
        if len(matches) > 1:
            raise DocumentParsingError(f"Duplicate school IPR table in section {section}")
        if not matches:
            continue
        table = matches[0]
        for index, row in enumerate(table.rows[1:], base_row):
            values = [normalize_space(cell.text) for cell in row.cells]
            if len(values) < len(kinds):
                raise DocumentParsingError(f"School IPR section {section} has too few columns")
            if not values[0]:
                continue
            for column, (value, kind) in enumerate(zip(values, kinds), 1):
                add(f"{section}[{index}][{column}]", value, kind)

    section8 = _section(paragraphs, 8)
    choices8 = [choice for text in section8[1:] if (choice := _selection(text)) is not None]
    if choices8:
        if len(choices8) < 8 or any(not comparison_key(choices8[i][1]).startswith(comparison_key(label))
                                   for i, label in enumerate(_ASSESSMENT_ROWS)):
            raise DocumentParsingError("School IPR assessment choices changed")
        for i, (checked, _) in enumerate(choices8[:8], 1):
            add(f"8[{i}][1]", "true" if checked else "false", "checkbox")
        if len(choices8) >= 9 and comparison_key(choices8[8][1]).startswith("інше"):
            checked, other_text = choices8[8]
            if not checked:
                add("8[9][0]", "false", "checkbox")
            else:
                detail = other_text[len("інше"):].strip(" _.:;")
                if detail:
                    add("8[9][0]", "true", "checkbox")
                    add("8[9][1]", detail, "textarea")

    signer = (_unique_suffix(paragraphs, "Я,") or "").rstrip(" ,.;")
    parents = next((text for text in paragraphs if text.startswith("прізвище, власне ім’я, по батькові (за наявності) батьків")), "")
    if signer and comparison_key(signer) in comparison_key(parents):
        add("footer_parents_names", signer, "textarea")
    return tuple(fields)
