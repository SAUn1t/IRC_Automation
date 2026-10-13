import re
import unicodedata
from dataclasses import dataclass

from .errors import WorkflowError


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
        raise WorkflowError("Enter exactly two words: first name and surname. Resolve multiword names manually before processing.")
    return ChildName(*parts)
