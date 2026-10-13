import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from zipfile import BadZipFile

from .errors import DocumentNotFound, DocumentParsingError, MultipleDocumentsFound
from .normalization import ChildName, comparison_key, normalize_space


def find_document(folder: Path, child: ChildName, patterns: tuple[str, ...]) -> Path:
    if not folder.is_dir():
        raise DocumentNotFound("Configured DOCX folder does not exist")
    names = {comparison_key(p.format(Name=child.first, Surname=child.surname)) for p in patterns}
    matches = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.casefold() == ".docx" and comparison_key(p.name) in names), key=lambda p: p.name)
    if not matches:
        raise DocumentNotFound("No exact DOCX filename match")
    if len(matches) > 1:
        raise MultipleDocumentsFound(f"{len(matches)} DOCX files match configured patterns; resolve this manually")
    return matches[0]


@dataclass(frozen=True)
class ParsedDocument:
    fields: dict[str, str]
    headings: tuple[str, ...]


_PAIR = re.compile(r"^\s*([^:\n]{1,120})\s*:\s*(.*)$", re.DOTALL)


def _clean(value: str) -> str:
    value = value.replace("☑", "yes").replace("☒", "yes").replace("☐", "no")
    return "\n".join(normalize_space(line) for line in value.splitlines()).strip()


def _add(fields: dict[str, str], label: str, value: str) -> None:
    key = comparison_key(label)
    if not key:
        return
    if key in fields:
        raise DocumentParsingError(f"Duplicate DOCX label: {label}")
    fields[key] = _clean(value)


def parse_document(path: Path) -> ParsedDocument:
    try:
        doc = Document(path)
        fields: dict[str, str] = {}
        headings: list[str] = []
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                if block.style and block.style.name.lower().startswith("heading"):
                    headings.append(_clean(text))
                else:
                    pair = _PAIR.match(text)
                    if pair:
                        _add(fields, pair.group(1), pair.group(2))
            elif isinstance(block, Table):
                for row in block.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if len(cells) >= 2 and cells[0]:
                        if len(cells) % 2 or any(not cells[i] for i in range(0, len(cells), 2)):
                            raise DocumentParsingError("Table row does not contain clear label/value pairs")
                        for i in range(0, len(cells), 2):
                            _add(fields, cells[i], cells[i + 1])
                    elif any(cells):
                        raise DocumentParsingError("Table row has a value without a label")
        if not fields:
            raise DocumentParsingError("No label/value pairs found in DOCX")
        return ParsedDocument(fields, tuple(headings))
    except DocumentParsingError:
        raise
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, PackageNotFoundError) as exc:
        raise DocumentParsingError("Cannot read or parse the DOCX") from exc
