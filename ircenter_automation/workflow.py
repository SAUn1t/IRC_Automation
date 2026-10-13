import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from .browser import BrowserSession, require_selectors
from .documents import find_document, parse_document
from .errors import AuthenticationRequired, ChildIdentityMismatch, Stopped, SubmissionNotConfirmed
from .form_filler import FormFiller
from .ircenter import IRCenter
from .mapping import load_mapping, map_document
from .normalization import comparison_key, parse_child_name
from .settings import Settings
from .state import State, StateMachine


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewSummary:
    child_name: str
    document_name: str
    populated: int
    verified: int
    warnings: tuple[str, ...]


class Workflow:
    def __init__(
        self, settings: Settings, on_status: Callable[[str], None],
        on_authentication: Callable[[], None], on_review: Callable[[ReviewSummary], None],
        stop_event: Event, continue_event: Event, submit_event: Event,
    ):
        self.settings = settings
        self.on_status = on_status
        self.on_authentication = on_authentication
        self.on_review = on_review
        self.stop_event = stop_event
        self.continue_event = continue_event
        self.submit_event = submit_event
        self.machine = StateMachine()

    def _advance(self, state: State, message: str) -> None:
        self.machine.advance(state)
        log.info("workflow_state=%s", state.name)
        self.on_status(message)
        self._check_stop()

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise Stopped("Stopped by user; nothing submitted")

    def _wait(self, event: Event) -> None:
        while not event.wait(0.2):
            self._check_stop()
        self._check_stop()

    def run(self, raw_name: str) -> str:
        try:
            child = parse_child_name(raw_name)
            self._advance(State.INPUT_VALIDATED, f"Normalized child name: {child.display}")
            document_path: Path = find_document(self.settings.docx_folder, child, self.settings.filename_patterns)
            self._advance(State.DOCUMENT_FOUND, f"Document found: {document_path.name}")
            require_selectors(self.settings.selectors, self.settings.manual_review_only)
            specs = load_mapping(self.settings.mapping_file)
            parsed = parse_document(document_path)
            if parsed.template == "school_ipr_2026":
                parts = parsed.fields[comparison_key("docx_child_full_name")].split(" ")
                if len(parts) != 3 or not child.matches(parts[1], parts[0]):
                    raise ChildIdentityMismatch("DOCX child name does not match the requested child")
            fields = map_document(parsed.fields, specs)
            with BrowserSession(self.settings) as browser:
                page = browser.open_site()
                self._advance(State.BROWSER_READY, "IR Center opened")
                site = IRCenter(page, self.settings.selectors, self.settings.timeout_ms)
                if not site.authenticated():
                    self.on_authentication()
                    self._wait(self.continue_event)
                    browser.verify_domain()
                    browser.open_site()
                    if not site.authenticated():
                        raise AuthenticationRequired("Sign in manually and press Continue after login")
                self._advance(State.AUTHENTICATED, "Conclusions journal confirmed")
                site.find_child(child)
                self._advance(State.CHILD_FOUND, "Exact child match found")
                browser.verify_domain()
                site.verify_child_identity(child)
                self._advance(State.CHILD_CONFIRMED, "Opened child identity confirmed")
                site.open_new_form()
                self._advance(State.FORM_REQUESTED, "New form requested")
                browser.verify_domain()
                site.verify_form_open(child)
                self._advance(State.FORM_OPEN_CONFIRMED, "Form opened and confirmed")
                self._advance(State.DOCUMENT_PARSED, f"{len(fields)} mapped DOCX fields parsed locally")
                filler = FormFiller(page)
                for index, field in enumerate(fields, 1):
                    self._check_stop()
                    filler.fill(field)
                    self.on_status(f"Fields filled and read back: {index}/{len(fields)}")
                self._advance(State.FORM_POPULATED, "All mapped fields populated")
                verification = filler.verify_all(fields)
                if not self.settings.manual_review_only:
                    site.check_validation_errors()
                self._advance(State.FORM_VERIFIED, f"Full verification passed: {len(verification)}/{len(fields)}")
                site.verify_child_identity(child, on_form=True)
                warnings = ("Only exact scalar fields were transferred. Complete and review all remaining IPR sections manually.",) if self.settings.manual_review_only else ()
                summary = ReviewSummary(child.display, document_path.name, len(fields), len(verification), warnings)
                if self.settings.manual_review_only:
                    self._advance(State.MANUAL_REVIEW, "Partial transfer verified. Complete and review all remaining sections in the browser. Press Stop when finished.")
                    self.on_review(summary)
                    self.stop_event.wait()
                    return "MANUAL REVIEW ENDED — submission status was not checked by the app"
                self._advance(State.READY_TO_SUBMIT, "Ready to submit" if not self.settings.dry_run else "Dry run verified; no submission")
                self.on_review(summary)
                if self.settings.dry_run:
                    return "DRY RUN COMPLETE — nothing submitted"
                if self.settings.review_before_submit:
                    self._wait(self.submit_event)
                browser.verify_domain()
                site.verify_child_identity(child, on_form=True)
                filler.verify_all(fields)
                site.check_validation_errors()
                self._advance(State.SUBMITTING, "Submitting once")
                try:
                    site.submit_once()
                    site.verify_submission()
                except Exception as exc:
                    self.on_status("SUBMISSION NOT CONFIRMED — inspect the open browser, then press Stop to close it. Do not retry blindly.")
                    self.stop_event.wait()
                    raise SubmissionNotConfirmed("SUBMISSION NOT CONFIRMED; inspect the site before any retry") from exc
                browser.verify_domain()
                self._advance(State.SUBMISSION_CONFIRMED, "Submission confirmed by website")
                self._advance(State.COMPLETED, "Completed")
                return "COMPLETED"
        except Exception:
            if self.machine.current not in (State.COMPLETED, State.ERROR):
                self.machine.advance(State.ERROR)
                log.info("workflow_state=ERROR")
            raise
