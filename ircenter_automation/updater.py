"""Check the project's Windows release and stage a verified installer."""

import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import __version__


RELEASE_API = "https://api.github.com/repos/SAUn1t/IRC_Automation/releases/latest"
ASSET_NAME = "IRCenterAssistant-Setup.exe"
MAX_INSTALLER_BYTES = 700 * 1024 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    """A release could not be safely checked or installed."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str


def _version_parts(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value)
    if not match:
        raise UpdateError("Release version is invalid")
    return tuple(int(part) for part in match.groups())


def parse_release(data: dict, current_version: str = __version__) -> Release | None:
    """Accept only newer tagged releases with the expected installer and digest."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise UpdateError("Release metadata is invalid")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise UpdateError("Release tag is invalid")
    newest = _version_parts(tag)
    if newest <= _version_parts(current_version):
        return None
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Release assets are missing")
    candidates = [item for item in assets if isinstance(item, dict) and item.get("name") == ASSET_NAME]
    if len(candidates) != 1:
        raise UpdateError("Windows installer is missing from the release")
    asset = candidates[0]
    url = asset.get("browser_download_url")
    expected_path = f"/SAUn1t/IRC_Automation/releases/download/{tag}/{ASSET_NAME}"
    parsed = urlparse(url) if isinstance(url, str) else None
    if (not parsed or parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.path != expected_path or parsed.query or parsed.fragment):
        raise UpdateError("Installer download URL is unexpected")
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise UpdateError("Release installer has no SHA-256 digest")
    return Release(tag[1:], url, digest[7:].lower())


def check_for_update(current_version: str = __version__) -> Release | None:
    request = Request(RELEASE_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"IRCenterAssistant/{current_version}",
    })
    try:
        with urlopen(request, timeout=12) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise UpdateError("Release metadata is too large")
        return parse_release(json.loads(payload), current_version)
    except UpdateError:
        raise
    except (OSError, ValueError) as exc:
        raise UpdateError("Could not check GitHub releases") from exc


def _verified_existing(path: Path, digest: str) -> bool:
    if not path.is_file() or path.stat().st_size > MAX_INSTALLER_BYTES:
        return False
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    return compare_digest(sha.hexdigest(), digest)


def download_update(release: Release, destination_dir: Path) -> Path:
    destination = destination_dir / f"IRCenterAssistant-Setup-{release.version}.exe"
    temporary: Path | None = None
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        if _verified_existing(destination, release.sha256):
            return destination
        with tempfile.NamedTemporaryFile(dir=destination_dir, prefix="installer-", suffix=".part", delete=False) as file:
            temporary = Path(file.name)
            request = Request(release.url, headers={"User-Agent": f"IRCenterAssistant/{__version__}"})
            with urlopen(request, timeout=30) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in (
                    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                ):
                    raise UpdateError("Installer download redirected to an unexpected host")
                sha = hashlib.sha256()
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_INSTALLER_BYTES:
                        raise UpdateError("Installer is too large")
                    sha.update(chunk)
                    file.write(chunk)
        if not compare_digest(sha.hexdigest(), release.sha256):
            raise UpdateError("Installer checksum did not match the GitHub release")
        os.replace(temporary, destination)
        return destination
    except UpdateError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise UpdateError("Could not download the update installer") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def launch_update(installer: Path) -> None:
    if sys.platform != "win32" or not installer.is_file():
        raise UpdateError("The Windows update installer is unavailable")
    try:
        subprocess.Popen([
            str(installer), "/VERYSILENT", "/SP-",
            "/NORESTART", "/CLOSEAPPLICATIONS",
        ], cwd=installer.parent, close_fds=True)
    except OSError as exc:
        raise UpdateError("Could not start the update installer") from exc
