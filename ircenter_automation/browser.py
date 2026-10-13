from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from .errors import ConfigurationError, WorkflowError
from .settings import Settings


class BrowserSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def __enter__(self) -> "BrowserSession":
        self.playwright = sync_playwright().start()
        try:
            profile: Path = self.settings.browser_profile
            profile.mkdir(parents=True, exist_ok=True)
            channel = None if self.settings.browser == "chromium" else self.settings.browser
            self.context = self.playwright.chromium.launch_persistent_context(
                str(profile), headless=self.settings.browser_headless, channel=channel,
                executable_path=str(self.settings.browser_executable) if self.settings.browser_executable else None,
                accept_downloads=False,
            )
            self.context.set_default_timeout(self.settings.timeout_ms)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            return self
        except Exception:
            self.playwright.stop()
            raise

    def __exit__(self, *_: object) -> None:
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def open_site(self) -> Page:
        assert self.page is not None
        self.page.goto(self.settings.website_url, wait_until="domcontentloaded")
        self.verify_domain()
        return self.page

    def verify_domain(self) -> None:
        assert self.page is not None
        if urlparse(self.page.url).hostname != "ircenter.gov.ua":
            raise WorkflowError("Browser is outside the configured IR Center domain; stopped")


REQUIRED_SELECTORS = (
    "search_input", "search_button", "result_rows", "no_results", "next_results_page", "result_first_name",
    "result_surname", "record_first_name", "record_surname", "add_form_button",
    "form_root", "form_heading", "form_heading_text", "form_child_first_name", "form_child_surname",
    "submit_button", "success_indicator", "validation_error",
)


def require_selectors(selectors: dict[str, str]) -> None:
    missing = [key for key in REQUIRED_SELECTORS if not selectors.get(key) or "REPLACE_" in selectors[key]]
    if missing:
        raise ConfigurationError("Inspect the live IR Center DOM and configure selectors: " + ", ".join(missing))
