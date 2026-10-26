import json
import string
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    docx_folder: Path
    filename_patterns: tuple[str, ...]
    website_url: str
    browser: str
    browser_transport: str
    extension_token: str | None
    browser_executable: Path | None
    browser_headless: bool
    browser_profile: Path
    timeout_ms: int
    review_before_submit: bool
    auto_submit: bool
    dry_run: bool
    manual_review_only: bool
    selectors: dict[str, str]
    mapping_file: Path
    document_source: str = "local"
    drive_folder_url: str = ""


def load_settings(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        folder = Path(data["docx_folder"]).expanduser()
        document_source = data.get("document_source", "local")
        if document_source not in ("local", "drive"):
            raise ValueError("document_source must be local or drive")
        drive_folder_url = data.get("drive_folder_url", "")
        if not isinstance(drive_folder_url, str):
            raise ValueError("drive_folder_url must be a Google Drive folder link")
        if drive_folder_url.strip():
            from .document_source import drive_folder_id
            drive_folder_id(drive_folder_url)
        profile = Path(data["browser_profile"]).expanduser()
        mapping = Path(data["mapping_file"]).expanduser()
        if not mapping.is_absolute():
            mapping = path.parent / mapping
        patterns = tuple(data["filename_patterns"])
        if not patterns:
            raise ValueError("At least one filename pattern is required")
        for pattern in patterns:
            fields = [part[1] for part in string.Formatter().parse(pattern) if part[1] is not None]
            if sorted(fields) != ["Name", "Surname"] or not pattern.lower().endswith(".docx"):
                raise ValueError("Each filename pattern needs {Name}, {Surname}, and .docx")
        url = str(data["website_url"])
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "ircenter.gov.ua":
            raise ValueError("website_url must use https://ircenter.gov.ua/")
        browser = str(data["browser"])
        if browser not in ("chromium", "chrome", "msedge"):
            raise ValueError("browser must be chromium, chrome, or msedge")
        browser_transport = str(data.get("browser_transport", "playwright"))
        if browser_transport not in ("playwright", "cdp", "extension"):
            raise ValueError("browser_transport must be playwright, cdp, or extension")
        if browser_transport in ("cdp", "extension") and browser == "chromium":
            raise ValueError("cdp and extension browser_transport need chrome or msedge")
        extension_token = data.get("extension_token")
        if extension_token is not None and (not isinstance(extension_token, str) or len(extension_token) < 24):
            raise ValueError("extension_token must be a long local pairing token or null")
        executable_value = data.get("browser_executable")
        if executable_value is not None and (not isinstance(executable_value, str) or not executable_value.strip()):
            raise ValueError("browser_executable must be a path or null")
        executable = Path(executable_value).expanduser() if executable_value else None
        headless = data.get("browser_headless", False)
        if type(headless) is not bool:
            raise ValueError("browser_headless must be true or false")
        timeout = int(data["timeout_ms"])
        if timeout < 1000 or timeout > 120000:
            raise ValueError("timeout_ms must be between 1000 and 120000")
        if any(type(data[key]) is not bool for key in ("review_before_submit", "auto_submit", "dry_run")):
            raise ValueError("Submission settings must be true or false")
        review = data["review_before_submit"]
        auto = data["auto_submit"]
        if review and auto:
            raise ValueError("Choose either review_before_submit or auto_submit")
        if not review and not auto and not data["dry_run"]:
            raise ValueError("Enable review_before_submit, auto_submit, or dry_run")
        manual_review_only = data.get("manual_review_only", False)
        if type(manual_review_only) is not bool:
            raise ValueError("manual_review_only must be true or false")
        return Settings(folder, patterns, url, browser, browser_transport, extension_token,
                        executable, headless, profile, timeout,
                        review, auto, data["dry_run"], manual_review_only, dict(data["selectors"]), mapping,
                        document_source, drive_folder_url.strip())
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Invalid settings file: {exc}") from exc
