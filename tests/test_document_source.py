import json
import shutil
from pathlib import Path

import pytest
from docx import Document

import ircenter_automation.document_source as source
from ircenter_automation.errors import ChildIdentityMismatch, DocumentNotFound, MultipleDocumentsFound
from ircenter_automation.manual_entry import prepare_manual_entry
from ircenter_automation.normalization import parse_child_name
from ircenter_automation.settings import load_settings


FOLDER = "application/vnd.google-apps.folder"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ROOT = "root123456789"
CLASS = "class123456789"
CHILD = "child123456789"
FILE = "file123456789"


def settings_file(tmp_path: Path, *, mode: str = "drive"):
    data = json.loads(Path("config/settings.example.json").read_text(encoding="utf-8"))
    data["document_source"] = mode
    data["drive_folder_url"] = f"https://drive.google.com/drive/folders/{ROOT}?usp=sharing"
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_settings(path)


def sample_docx(path: Path, full_name: str = "Шевченко Іван Петрович"):
    doc = Document()
    for line in (
        "1. Період виконання з 01.09.2026 по 31.05.2027",
        f"прізвище, власне ім’я, по батькові(за наявності) {full_name}",
        "контактні номери телефонів батьків (інших законних представників) учня 000 000 000",
        "клас навчання 7-А", "рік навчання 7",
        "5. Створення інклюзивного освітнього середовища, зокрема:",
        "11. Погодження індивідуальної програми розвитку з батьками",
    ):
        doc.add_paragraph(line)
    doc.save(path)


def fake_drive(monkeypatch, docx_path: Path, *, files=None, child_folders=None):
    calls = []
    structure = {
        ROOT: [(CLASS, "7-А", FOLDER), ("other123456789", "6-Б", FOLDER)],
        CLASS: child_folders if child_folders is not None else [
            (CHILD, "Шевченко Іван Петрович", FOLDER),
            ("otherchild12345", "Петренко Олена Петрівна", FOLDER),
        ],
        CHILD: files if files is not None else [
            (FILE, "ІПР 2026.docx", DOCX),
            ("otherfile12345", "Протокол.docx", DOCX),
        ],
    }

    def list_children(folder_id, resource_key=""):
        calls.append(folder_id)
        return structure[folder_id]

    def download(*, id, output, quiet, use_cookies):
        assert id == FILE
        assert quiet and not use_cookies
        shutil.copyfile(docx_path, output)
        return output

    monkeypatch.setattr(source, "_list_children", list_children)
    monkeypatch.setattr(source.gdown, "download", download)
    return calls


def test_remote_uses_class_then_child_folder_and_only_ipr_docx(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.docx"
    sample_docx(path)
    calls = fake_drive(monkeypatch, path)
    settings = settings_file(tmp_path)
    entered = parse_child_name("Іван Шевченко")
    with source.open_document(settings, entered, "7-A") as found:
        downloaded_path = found.path
        assert downloaded_path.is_file()
        assert found.name == "ІПР 2026.docx"
    assert calls == [ROOT, CLASS, CHILD]
    assert not downloaded_path.exists()
    guide = prepare_manual_entry(settings, "Шевченко Іван", "7-A")
    assert guide.child_name == "Іван Шевченко"
    assert guide.document_name == "ІПР 2026.docx"


def test_remote_stops_on_ambiguous_child_or_ipr(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.docx"
    sample_docx(path)
    settings = settings_file(tmp_path)
    fake_drive(monkeypatch, path, child_folders=[
        (CHILD, "Шевченко Іван Петрович", FOLDER),
        ("another12345678", "Шевченко Іван Андрійович", FOLDER),
    ])
    with pytest.raises(MultipleDocumentsFound, match="child folders"):
        prepare_manual_entry(settings, "Іван Шевченко", "7-A")
    fake_drive(monkeypatch, path, files=[
        (FILE, "ІПР осінь.docx", DOCX), ("second12345678", "ІПР весна.docx", DOCX),
    ])
    with pytest.raises(MultipleDocumentsFound, match="ІПР DOCX"):
        prepare_manual_entry(settings, "Іван Шевченко", "7-A")


def test_remote_stops_if_class_or_document_identity_differs(tmp_path: Path, monkeypatch):
    path = tmp_path / "sample.docx"
    sample_docx(path, "Петренко Олена Петрівна")
    fake_drive(monkeypatch, path)
    settings = settings_file(tmp_path)
    with pytest.raises(DocumentNotFound, match="Class folder"):
        prepare_manual_entry(settings, "Іван Шевченко", "8-А")
    with pytest.raises(ChildIdentityMismatch):
        prepare_manual_entry(settings, "Іван Шевченко", "7-А")


@pytest.mark.parametrize("url", [
    "http://drive.google.com/drive/folders/root123456789",
    "https://example.com/drive/folders/root123456789",
    "https://drive.google.com/file/d/file123456789/view",
])
def test_drive_link_must_be_a_folder(url):
    with pytest.raises(ValueError):
        source.drive_folder_id(url)


def test_public_folder_page_listing_is_parsed_without_recursion(monkeypatch):
    payload = [[
        [CLASS, None, "7-А", FOLDER],
        ["other123456789", None, "6-Б", FOLDER],
    ], None]
    html = ("<html><head><title>Shared - Google Drive</title></head><body>"
            "<script>window['_DRIVE_ivd'] = '" + json.dumps(payload, ensure_ascii=False) +
            "';</script></body></html>")

    class Response:
        text = html

        def raise_for_status(self):
            pass

    def get(url, *, params, headers, timeout):
        assert url.endswith(ROOT)
        assert params["hl"] == "en" and timeout == 25
        return Response()

    monkeypatch.setattr(source.requests, "get", get)
    children = source._list_children(ROOT)
    assert children == [(CLASS, "7-А", FOLDER), ("other123456789", "6-Б", FOLDER)]
