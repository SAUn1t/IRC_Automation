"""Run the exact-field workflow inside the user's already signed-in Chrome."""

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
        warnings = ["Review every filled field and complete any missing IPR sections manually."]
        if guide.portal_fields and not any(field.name == "9[1][1]" for field in guide.portal_fields):
            warnings.append("Section 9 has no selected DOCX answer; check the portal's default before generating.")
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
