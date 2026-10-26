import re
import unicodedata
from dataclasses import dataclass

from .errors import ChildIdentityMismatch, WorkflowError


def normalize_space(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def comparison_key(value: str) -> str:
    return unicodedata.normalize("NFC", normalize_space(value).casefold())


@dataclass(frozen=True)
class ChildName:
    first: str
    surname: str

    @property
    def display(self) -> str:
        return f"{self.first} {self.surname}"

    def matches(self, first: str, surname: str) -> bool:
        return comparison_key(self.first) == comparison_key(first) and comparison_key(self.surname) == comparison_key(surname)


def parse_child_name(raw: str) -> ChildName:
    parts = normalize_space(raw).split(" ")
    if len(parts) != 2 or not all(parts) or any(re.search(r"\d", part) for part in parts):
        raise WorkflowError("Enter exactly two name words. Resolve multiword names manually before processing.")
    return ChildName(*parts)


_SCHOOL_NAME_LABEL = re.compile(
    r"^прізвище,\s*власне ім[’ʼ']я,\s*по батькові(?:\s*\(за наявності\))?\s+(.+)$",
    re.IGNORECASE,
)


def labeled_school_full_name(value: str) -> str | None:
    match = _SCHOOL_NAME_LABEL.fullmatch(normalize_space(value))
    if not match:
        return None
    name = normalize_space(match.group(1))
    return name if len(name.split(" ")) == 3 else None


def resolve_two_word_name(entered: ChildName, surname_first_patronymic: str) -> ChildName:
    parts = normalize_space(surname_first_patronymic).split(" ")
    if len(parts) != 3:
        raise ChildIdentityMismatch("DOCX child name is not a clear three-part full name")
    surname, first, _patronymic = parts
    if not (entered.matches(first, surname) or entered.matches(surname, first)):
        raise ChildIdentityMismatch("DOCX child name does not match the two entered words")
    return ChildName(first, surname)
