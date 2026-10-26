"""Find one DOCX in a local folder or a public Drive class/child folder."""

import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterator
from urllib.parse import parse_qs, urlparse

import gdown
import requests
from gdown.download_folder import _parse_google_drive_file
from gdown.exceptions import FileURLRetrievalError

from .documents import find_document
from .errors import DocumentNotFound, DocumentParsingError, MultipleDocumentsFound, WorkflowError
from .normalization import ChildName, comparison_key, normalize_space

if TYPE_CHECKING:
    from .settings import Settings


_FOLDER_PATH = re.compile(r"^/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]{10,200})/?$")
_FOLDER_ID = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
_WORD = re.compile(r"[^\W_]+(?:[-'’ʼ][^\W_]+)*", re.UNICODE)
_MAX_DOCX_BYTES = 32 * 1024 * 1024
_FOLDER_MIME = "application/vnd.google-apps.folder"
_DRIVE_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}


@dataclass(frozen=True)
class LocatedDocument:
    path: Path
    name: str


def drive_folder_id(url: str) -> str:
    parsed = urlparse(url.strip())
    match = _FOLDER_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "drive.google.com" or not match or parsed.fragment:
        raise ValueError("Use a Google Drive parent folder link from drive.google.com/drive/folders/...")
    return match.group(1)


def _class_key(value: str) -> str:
    # Latin and Cyrillic A are commonly interchanged when typing a class name.
    return re.sub(r"[\s‐‑‒–—-]+", "", comparison_key(value)).replace("а", "a")


def _word_key(value: str) -> str:
    return comparison_key(value).replace("’", "'").replace("ʼ", "'")


def _child_folder_matches(name: str, child: ChildName) -> bool:
    tokens = [_word_key(token) for token in _WORD.findall(name)]
    first, surname = _word_key(child.first), _word_key(child.surname)
    return len(tokens) >= 2 and tuple(tokens[:2]) in ((first, surname), (surname, first))


def _list_children(folder_id: str, resource_key: str = "") -> list[tuple[str, str, str]]:
    if not _FOLDER_ID.fullmatch(folder_id):
        raise WorkflowError("Google Drive returned an invalid folder identifier")
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    params = {"hl": "en"}
    if resource_key:
        params["resourcekey"] = resource_key
    try:
        response = requests.get(url, params=params, headers=_DRIVE_HEADERS, timeout=25)
        response.raise_for_status()
        # gdown's pinned public-folder parser reads Google's embedded folder listing.
        _folder, children = _parse_google_drive_file(url, response.text)
        if len(children) >= 50:
            raise WorkflowError("A Google Drive folder contains at least 50 items and may be truncated; split it into smaller folders")
        return list(children)
    except WorkflowError:
        raise
    except (requests.RequestException, RuntimeError, ValueError, TypeError, IndexError) as exc:
        raise WorkflowError("Could not list a Google Drive folder; check its Anyone with the link sharing") from exc


def _remote_match(settings: "Settings", child: ChildName, class_name: str):
    if not class_name or not normalize_space(class_name):
        raise WorkflowError("Enter the class folder name, such as 7-A, for Google Drive mode")
    if not settings.drive_folder_url:
        raise WorkflowError("Paste and save the Google Drive parent folder link")
    root_id = drive_folder_id(settings.drive_folder_url)
    keys = parse_qs(urlparse(settings.drive_folder_url).query).get("resourcekey", [])
    classes = [(id, name) for id, name, mime in _list_children(root_id, keys[0] if len(keys) == 1 else "")
               if mime == _FOLDER_MIME and _class_key(name) == _class_key(class_name)]
    if not classes:
        raise DocumentNotFound("Class folder was not found in the linked Google Drive parent folder")
    if len(classes) > 1:
        raise MultipleDocumentsFound("Multiple Google Drive class folders have that name")
    children = [(id, name) for id, name, mime in _list_children(classes[0][0])
                if mime == _FOLDER_MIME and _child_folder_matches(name, child)]
    if not children:
        raise DocumentNotFound("Child folder was not found in that Google Drive class folder")
    if len(children) > 1:
        raise MultipleDocumentsFound("Multiple child folders match those two name words in that class")
    files = [(id, name) for id, name, mime in _list_children(children[0][0])
             if mime != _FOLDER_MIME and Path(name).suffix.casefold() == ".docx"
             and ("іпр" in comparison_key(name) or "ipr" in comparison_key(name))]
    if not files:
        raise DocumentNotFound("No DOCX with ІПР in its name was found in the child folder")
    if len(files) > 1:
        raise MultipleDocumentsFound("Multiple ІПР DOCX files are in the child folder; resolve this manually")
    return files[0]


@contextmanager
def open_document(settings: "Settings", child: ChildName, class_name: str = "") -> Iterator[LocatedDocument]:
    """Yield a local path and delete a remote download when parsing is done."""
    if settings.document_source == "local":
        path = find_document(settings.docx_folder, child, settings.filename_patterns)
        yield LocatedDocument(path, path.name)
        return
    file_id, name = _remote_match(settings, child, class_name)
    with tempfile.TemporaryDirectory(prefix="ircenter-doc-") as directory:
        path = Path(directory) / "source.docx"
        try:
            downloaded = gdown.download(id=file_id, output=str(path), quiet=True, use_cookies=False)
        except (requests.RequestException, FileURLRetrievalError, OSError, ValueError) as exc:
            raise WorkflowError("Could not download the matching Google Drive DOCX") from exc
        if not downloaded or not path.is_file():
            raise WorkflowError("Could not download the matching Google Drive DOCX")
        if path.stat().st_size > _MAX_DOCX_BYTES:
            raise DocumentParsingError("Google Drive DOCX exceeds the 32 MB document limit")
        yield LocatedDocument(path, name)
