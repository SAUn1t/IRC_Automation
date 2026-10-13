"""Run the exact-field workflow inside the user's already signed-in Chrome."""

import subprocess
import time
from threading import Event
from typing import Callable

from .browser import BrowserSession
from .errors import Stopped, WorkflowError
from .extension_bridge import ExtensionBridge
from .manual_entry import prepare_manual_entry
from .settings import Settings
from .workflow import ReviewSummary


class ExtensionWorkflow:
    def __init__(
        self, settings: Settings, on_status: Callable[[str], None],
        on_review: Callable[[ReviewSummary], None], stop_event: Event,
    ):
        self.settings = settings
        self.on_status = on_status
        self.on_review = on_review
        self.stop_event = stop_event

    def run(self, raw_name: str) -> str:
        guide = prepare_manual_entry(self.settings, raw_name)
        summary = ReviewSummary(
            guide.child_name, guide.document_name, len(guide.fields), len(guide.fields),
            ("Only four exact fields were transferred. Review and complete the remaining IPR sections manually.",),
        )
        with ExtensionBridge(self.settings.extension_token, guide) as bridge:
            browser = BrowserSession(self.settings)._browser_executable()
            try:
                subprocess.Popen(
                    [str(browser), self.settings.website_url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise WorkflowError("Could not open the installed Chrome browser") from exc
            self.on_status("Chrome opened. Waiting for the paired extension on the conclusions journal.")
            reminder_at = time.monotonic() + 30
            while True:
                if self.stop_event.is_set():
                    raise Stopped("Stopped by user; nothing submitted by the app")
                status = bridge.next_status()
                if status:
                    kind, detail = status
                    if kind == "error":
                        raise WorkflowError("Chrome extension stopped: " + detail)
                    self.on_status(detail)
                    if kind == "ready":
                        self.on_review(summary)
                        return "MANUAL REVIEW — four fields filled in Chrome; no document submitted by the app"
                elif time.monotonic() >= reminder_at:
                    self.on_status(
                        "Still waiting for Chrome. Check that the extension is installed and paired, "
                        "and the conclusions journal is visible. Press Stop if needed."
                    )
                    reminder_at = time.monotonic() + 30
