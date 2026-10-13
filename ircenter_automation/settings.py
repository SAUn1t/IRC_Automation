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
    browser_executable: Path | None
    browser_headless: bool
    browser_profile: Path
    timeout_ms: int
    review_before_submit: bool
    auto_submit: bool
    dry_run: bool
    selectors: dict[str, str]
    mapping_file: Path


def load_settings(path: Path) -> Settings:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        folder = Path(data["docx_folder"]).expanduser()
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
        return Settings(folder, patterns, url, browser, executable, headless, profile, timeout, review, auto, data["dry_run"], dict(data["selectors"]), mapping)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Invalid settings file: {exc}") from exc
