import hashlib
import io
from pathlib import Path

import pytest

import ircenter_automation.updater as updater
from ircenter_automation.updater import Release, UpdateError, download_update, launch_update, parse_release


def _release(version: str, content: bytes = b"installer") -> dict:
    return {
        "tag_name": "v" + version, "draft": False, "prerelease": False,
        "assets": [{
            "name": "IRCenterAssistant-Setup.exe",
            "browser_download_url": (
                f"https://github.com/SAUn1t/IRC_Automation/releases/download/v{version}/"
                "IRCenterAssistant-Setup.exe"
            ),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        }],
    }


def test_update_accepts_only_newer_expected_release():
    assert parse_release(_release("1.0.0"), "1.0.0") is None
    release = parse_release(_release("1.0.1"), "1.0.0")
    assert release.version == "1.0.1"
    assert release.sha256 == hashlib.sha256(b"installer").hexdigest()


@pytest.mark.parametrize("change", [
    lambda data: data.update(tag_name="v1.0.1-beta"),
    lambda data: data["assets"][0].update(digest=None),
    lambda data: data["assets"][0].update(browser_download_url="https://example.com/installer.exe"),
    lambda data: data["assets"].append(data["assets"][0].copy()),
])
def test_update_rejects_untrusted_metadata(change):
    data = _release("1.0.1")
    change(data)
    with pytest.raises(UpdateError):
        parse_release(data, "1.0.0")


class FakeDownload(io.BytesIO):
    def __init__(self, content: bytes, url: str):
        super().__init__(content)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_update_download_verifies_digest_before_exposing_installer(monkeypatch, tmp_path: Path):
    content = b"test installer bytes"
    release = parse_release(_release("1.0.1", content), "1.0.0")
    calls = []

    def fake_open(request, timeout):
        calls.append(request.full_url)
        return FakeDownload(content, "https://release-assets.githubusercontent.com/download/test")

    monkeypatch.setattr(updater, "urlopen", fake_open)
    installer = download_update(release, tmp_path)
    assert installer.read_bytes() == content
    assert download_update(release, tmp_path) == installer
    assert calls == [release.url]


def test_update_bad_digest_removes_partial_download(monkeypatch, tmp_path: Path):
    release = Release("1.0.1", _release("1.0.1")["assets"][0]["browser_download_url"], "0" * 64)
    monkeypatch.setattr(updater, "urlopen", lambda *_args, **_kwargs: FakeDownload(
        b"wrong bytes", "https://release-assets.githubusercontent.com/download/test",
    ))
    with pytest.raises(UpdateError, match="checksum"):
        download_update(release, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_update_launches_installer_without_setup_prompts(monkeypatch, tmp_path: Path):
    installer = tmp_path / "IRCenterAssistant-Setup.exe"
    installer.write_bytes(b"verified separately")
    calls = []
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    launch_update(installer)
    command = calls[0][0][0]
    assert command[0] == str(installer)
    assert {"/VERYSILENT", "/SP-", "/NORESTART", "/CLOSEAPPLICATIONS"} <= set(command)
    assert calls[0][1]["cwd"] == tmp_path
