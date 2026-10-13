import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .errors import ConfigurationError, WorkflowError
from .settings import Settings


class BrowserSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.external_browser: Browser | None = None
        self.browser_process: subprocess.Popen | None = None

    def _browser_executable(self) -> Path:
        if self.settings.browser_executable:
            executable = self.settings.browser_executable
            if executable.is_file():
                return executable
            raise ConfigurationError(f"Browser executable does not exist: {executable}")
        names = ("chrome.exe", "chrome", "google-chrome", "google-chrome-stable") if self.settings.browser == "chrome" else (
            "msedge.exe", "msedge", "microsoft-edge")
        candidates = [Path(found) for name in names if (found := shutil.which(name))]
        if self.settings.browser == "chrome":
            candidates += [Path(base) / "Google/Chrome/Application/chrome.exe"
                           for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
                           if (base := os.environ.get(key))]
            candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        else:
            candidates += [Path(base) / "Microsoft/Edge/Application/msedge.exe"
                           for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
                           if (base := os.environ.get(key))]
            candidates.append(Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise ConfigurationError("Installed Chrome or Edge was not found; set browser_executable in settings.json")

    def _launch_normal_browser(self, profile_root: Path) -> None:
        assert self.playwright is not None
        profile = profile_root / f"{self.settings.browser}-normal-window"
        profile.mkdir(parents=True, exist_ok=True)
        port_file = profile / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        command = [
            str(self._browser_executable()), f"--user-data-dir={profile}",
            "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
            "--no-first-run", "--no-default-browser-check",
        ]
        if self.settings.browser_headless:
            command.append("--headless=new")
        command.append(self.settings.website_url)
        self.browser_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        port = None
        while time.monotonic() < deadline:
            if port_file.exists():
                lines = port_file.read_text(encoding="utf-8").splitlines()
                if lines and lines[0].isdigit():
                    port = int(lines[0])
                    break
            if self.browser_process.poll() is not None:
                break
            time.sleep(0.1)
        if port is None:
            raise WorkflowError(
                "Chrome/Edge did not open its local control port. Close an older app browser window "
                "or check browser_executable, then retry."
            )
        self.external_browser = self.playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}", timeout=self.settings.timeout_ms
        )
        contexts = self.external_browser.contexts
        if len(contexts) != 1:
            raise WorkflowError("Expected one normal-browser profile context")
        self.context = contexts[0]
        page_deadline = time.monotonic() + 5
        while time.monotonic() < page_deadline:
            self.page = next(
                (page for page in self.context.pages
                 if urlparse(page.url).hostname == "ircenter.gov.ua" or page.url == self.settings.website_url), None
            )
            if self.page is not None:
                break
            time.sleep(0.1)
        pages = self.context.pages
        if self.page is None:
            self.page = pages[0] if pages else self.context.new_page()

    def _close_normal_browser(self) -> None:
        if self.external_browser:
            try:
                self.external_browser.close()
            except Exception:
                pass
            self.external_browser = None
        if self.browser_process:
            if self.browser_process.poll() is None:
                self.browser_process.terminate()
                try:
                    self.browser_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.browser_process.kill()
            self.browser_process = None

    def __enter__(self) -> "BrowserSession":
        self.playwright = sync_playwright().start()
        try:
            profile: Path = self.settings.browser_profile
            profile.mkdir(parents=True, exist_ok=True)
            if self.settings.browser_transport == "cdp":
                self._launch_normal_browser(profile)
            else:
                channel = None if self.settings.browser == "chromium" else self.settings.browser
                self.context = self.playwright.chromium.launch_persistent_context(
                    str(profile), headless=self.settings.browser_headless, channel=channel,
                    executable_path=str(self.settings.browser_executable) if self.settings.browser_executable else None,
                    accept_downloads=False,
                )
            self.context.set_default_timeout(self.settings.timeout_ms)
            self.page = self.page or (self.context.pages[0] if self.context.pages else self.context.new_page())
            return self
        except Exception:
            self._close_normal_browser()
            self.playwright.stop()
            raise

    def __exit__(self, *_: object) -> None:
        if self.settings.browser_transport == "cdp":
            self._close_normal_browser()
        elif self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def open_site(self) -> Page:
        assert self.page is not None
        current = urlparse(self.page.url)
        already_open = self.page.url.startswith(self.settings.website_url) or (
            current.hostname == "ircenter.gov.ua" and current.path.startswith("/cdn-cgi/")
        )
        if not (self.settings.browser_transport == "cdp" and already_open):
            self.page.goto(self.settings.website_url, wait_until="domcontentloaded")
        self.verify_domain()
        return self.page

    def verify_domain(self) -> None:
        assert self.page is not None
        if urlparse(self.page.url).hostname != "ircenter.gov.ua":
            raise WorkflowError("Browser is outside the configured IR Center domain; stopped")


COMMON_SELECTORS = (
    "result_rows", "next_results_page", "add_form_button",
    "form_root", "form_heading", "form_heading_text", "submit_button",
)


def require_selectors(selectors: dict[str, str], manual_review_only: bool = False) -> None:
    list_mode = selectors.get("navigation_mode") == "conclusions_list"
    required = COMMON_SELECTORS + (("auth_indicator", "list_table") if list_mode else
                                   ("search_input", "search_button", "no_results"))
    if not manual_review_only:
        required += ("success_indicator", "validation_error")
    if selectors.get("record_full_name") and "REPLACE_" not in selectors["record_full_name"]:
        if selectors.get("record_name_format") != "surname_first_patronymic":
            required += ("record_name_format",)
    else:
        required += ("record_first_name", "record_surname")
    if selectors.get("form_child_full_name") and "REPLACE_" not in selectors["form_child_full_name"]:
        required += ("form_child_name_format",)
    else:
        required += ("form_child_first_name", "form_child_surname")
    missing = [key for key in required if not selectors.get(key) or "REPLACE_" in selectors[key]]
    if selectors.get("form_child_full_name") and selectors.get("form_child_name_format") != "surname_first_patronymic":
        missing.append("form_child_name_format=surname_first_patronymic")
    if selectors.get("result_full_name") and "REPLACE_" not in selectors["result_full_name"]:
        if selectors.get("result_name_format") != "surname_first_patronymic":
            missing.append("result_name_format=surname_first_patronymic")
        for key in ("result_open", "result_action"):
            if not selectors.get(key) or "REPLACE_" in selectors[key]:
                missing.append(key)
    else:
        for key in ("result_first_name", "result_surname"):
            if not selectors.get(key) or "REPLACE_" in selectors[key]:
                missing.append(key)
    if missing:
        raise ConfigurationError("Inspect the live IR Center DOM and configure selectors: " + ", ".join(missing))
