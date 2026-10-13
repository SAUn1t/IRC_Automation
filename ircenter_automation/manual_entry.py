"""Prepare a small, local copy guide for the supported school IPR layout."""

from dataclasses import dataclass
from pathlib import Path

from .documents import find_document, parse_document
from .errors import DocumentParsingError
from .normalization import comparison_key, parse_child_name, resolve_two_word_name
from .settings import Settings


@dataclass(frozen=True)
class ManualField:
    label: str
    portal_name: str
    value: str


@dataclass(frozen=True)
class ManualEntryGuide:
    child_name: str
    document_name: str
    fields: tuple[ManualField, ...]


_EXACT_FIELDS = (
    ("Період виконання", "execution_period"),
    ("Рік навчання", "year_of_study"),
    ("Клас навчання", "child_grade"),
    ("Телефони батьків", "parents_phones"),
)


def prepare_manual_entry(settings: Settings, raw_name: str) -> ManualEntryGuide:
    entered = parse_child_name(raw_name)
    path: Path = find_document(settings.docx_folder, entered, settings.filename_patterns)
    parsed = parse_document(path)
    if parsed.template != "school_ipr_2026":
        raise DocumentParsingError("Manual entry guide supports only the 11-section school IPR DOCX")
    child = resolve_two_word_name(entered, parsed.fields[comparison_key("docx_child_full_name")])
    fields = tuple(
        ManualField(label, portal_name, parsed.fields[comparison_key(portal_name)])
        for label, portal_name in _EXACT_FIELDS
    )
    return ManualEntryGuide(child.display, path.name, fields)
