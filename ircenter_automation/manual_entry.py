"""Prepare a small, local copy guide for the supported school IPR layout."""

from dataclasses import dataclass
from .documents import parse_document
from .document_source import open_document
from .errors import DocumentParsingError
from .normalization import comparison_key, parse_child_name, resolve_two_word_name
from .settings import Settings
from .school_ipr_2026 import PortalField, extract_portal_fields


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
    portal_fields: tuple[PortalField, ...] = ()


_EXACT_FIELDS = (
    ("Період виконання", "execution_period"),
    ("Рік навчання", "year_of_study"),
    ("Клас навчання", "child_grade"),
    ("Телефони батьків", "parents_phones"),
)


def prepare_manual_entry(settings: Settings, raw_name: str, class_name: str = "") -> ManualEntryGuide:
    entered = parse_child_name(raw_name)
    with open_document(settings, entered, class_name) as source:
        parsed = parse_document(source.path)
        if parsed.template != "school_ipr_2026":
            raise DocumentParsingError("Manual entry guide supports only the 11-section school IPR DOCX")
        child = resolve_two_word_name(entered, parsed.fields[comparison_key("docx_child_full_name")])
        fields = tuple(
            ManualField(label, portal_name, parsed.fields[comparison_key(portal_name)])
            for label, portal_name in _EXACT_FIELDS
        )
        base = {field.portal_name: field.value for field in fields}
        return ManualEntryGuide(child.display, source.name, fields,
                                extract_portal_fields(source.path, base))
