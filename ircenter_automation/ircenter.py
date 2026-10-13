from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .errors import (
    ChildIdentityMismatch, ChildNotFound, FormButtonNotFound, FormNotOpened,
    MultipleChildrenFound, SubmissionNotConfirmed, VerificationError,
)
from .normalization import ChildName, comparison_key, normalize_space


class IRCenter:
    def __init__(self, page: Page, selectors: dict[str, str], timeout_ms: int):
        self.page = page
        self.s = selectors
        self.timeout_ms = timeout_ms

    def authenticated(self) -> bool:
        try:
            self.page.locator(self.s["search_input"]).wait_for(state="visible", timeout=1500)
            return True
        except PlaywrightTimeout:
            return False

    def find_child(self, child: ChildName) -> None:
        self.page.locator(self.s["search_input"]).fill(child.display)
        self.page.locator(self.s["search_button"]).click()
        rows = self.page.locator(self.s["result_rows"])
        none = self.page.locator(self.s["no_results"])
        rows.first.or_(none).first.wait_for(state="visible", timeout=self.timeout_ms)
        next_page = self.page.locator(self.s["next_results_page"])
        if any(next_page.nth(i).is_visible() and next_page.nth(i).is_enabled() for i in range(next_page.count())):
            raise MultipleChildrenFound("Search results span multiple pages; complete identity review is required")
        if none.is_visible() and rows.count() == 0:
            raise ChildNotFound("Child not found")
        matches = []
        for i in range(rows.count()):
            row = rows.nth(i)
            first = row.locator(self.s["result_first_name"]).inner_text()
            surname = row.locator(self.s["result_surname"]).inner_text()
            if child.matches(first, surname):
                matches.append(row)
        if not matches:
            raise ChildNotFound("Child not found: no exact first name and surname match")
        if len(matches) > 1:
            details = "; ".join(normalize_space(row.inner_text())[:200] for row in matches)
            raise MultipleChildrenFound(f"{len(matches)} exact same-name records; additional identification is required. Visible records: {details}")
        matches[0].click()

    def verify_child_identity(self, child: ChildName, *, on_form: bool = False) -> None:
        prefix = "form_child_" if on_form else "record_"
        first_element = self.page.locator(self.s[prefix + "first_name"])
        surname_element = self.page.locator(self.s[prefix + "surname"])
        if first_element.count() != 1 or surname_element.count() != 1:
            raise ChildIdentityMismatch("Child identity fields are missing or ambiguous")
        first = normalize_space(first_element.inner_text())
        surname = normalize_space(surname_element.inner_text())
        if not child.matches(first, surname):
            raise ChildIdentityMismatch("Opened page does not belong to the requested child")

    def open_new_form(self) -> None:
        button = self.page.locator(self.s["add_form_button"])
        if button.count() != 1 or not button.is_visible() or not button.is_enabled():
            raise FormButtonNotFound("The add-form action is missing or ambiguous")
        button.click()

    def verify_form_open(self, child: ChildName) -> None:
        try:
            self.page.locator(self.s["form_root"]).wait_for(state="visible", timeout=self.timeout_ms)
            if self.page.locator(self.s["form_root"]).count() != 1:
                raise FormNotOpened("Expected form root is ambiguous")
            heading = self.page.locator(self.s["form_heading"])
            submit = self.page.locator(self.s["submit_button"])
            if heading.count() != 1 or not heading.is_visible() or comparison_key(heading.inner_text()) != comparison_key(self.s["form_heading_text"]):
                raise FormNotOpened("Expected form heading does not match")
            if submit.count() != 1 or not submit.is_visible():
                raise FormNotOpened("Expected form submit control is absent")
            self.verify_child_identity(child, on_form=True)
        except PlaywrightTimeout as exc:
            raise FormNotOpened("Expected new form did not appear") from exc

    def check_validation_errors(self) -> None:
        errors = self.page.locator(self.s["validation_error"])
        if any(errors.nth(i).is_visible() for i in range(errors.count())):
            raise VerificationError("The website reports validation errors")

    def submit_once(self) -> None:
        if self.page.locator(self.s["success_indicator"]).is_visible():
            raise VerificationError("Success indicator was already visible before submission")
        button = self.page.locator(self.s["submit_button"])
        if button.count() != 1 or not button.is_visible() or not button.is_enabled():
            raise VerificationError("Submit control is missing or disabled")
        button.click()

    def verify_submission(self) -> None:
        try:
            self.page.locator(self.s["success_indicator"]).wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightTimeout as exc:
            raise SubmissionNotConfirmed("Submission not confirmed; inspect the site before any retry") from exc
