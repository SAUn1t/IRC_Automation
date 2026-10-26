"""Run the exact-field workflow inside the user's already signed-in Chrome."""

import re
import time
from threading import Event
from typing import Callable

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

    def run(self, raw_name: str, class_name: str = "") -> str:
        guide = prepare_manual_entry(self.settings, raw_name, class_name)
        field_count = len(guide.portal_fields or guide.fields)
        warnings = [
            "Review every filled field and complete any missing IPR sections manually.",
            "Section 9 was skipped; check the portal's default before generating.",
        ]
        if any(re.fullmatch(r"5\[(?:29|[3-9]\d+)\]\[2\]", field.name)
               for field in guide.portal_fields):
            warnings.append("Review subject adaptation details; the portal dropdown stores only Adaptation or Modification.")
        summary = ReviewSummary(
            guide.child_name, guide.document_name, field_count, field_count,
            tuple(warnings),
        )
        with ExtensionBridge(self.settings.extension_token, guide) as bridge:
            self.on_status("Waiting for the extension in your signed-in Chrome profile to open the portal.")
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
                        return f"MANUAL REVIEW — {field_count} fields filled in Chrome; no document submitted by the app"
                elif time.monotonic() >= reminder_at:
                    self.on_status(
                        "Still waiting for Chrome. Keep your usual Chrome profile open and check "
                        "that the extension is installed, reloaded, and paired. Press Stop if needed."
                    )
                    reminder_at = time.monotonic() + 30
