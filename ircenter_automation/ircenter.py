import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from .errors import (
    ChildIdentityMismatch, ChildNotFound, FormButtonNotFound, FormNotOpened,
    MultipleChildrenFound, SubmissionNotConfirmed, VerificationError,
)
from .normalization import ChildName, comparison_key, labeled_school_full_name, normalize_space


class IRCenter:
    def __init__(self, page: Page, selectors: dict[str, str], timeout_ms: int):
        self.page = page
        self.s = selectors
        self.timeout_ms = timeout_ms
        self.selected_ipr_href: str | None = None

    @staticmethod
    def _full_name_identity(value: str) -> tuple[str, str]:
        parts = normalize_space(value).split(" ")
        if len(parts) != 3:
            raise ChildIdentityMismatch("Cannot safely parse surname, first name, and patronymic")
        return parts[1], parts[0]

    def _result_identity(self, row) -> tuple[str, str]:
        full_name_selector = self.s.get("result_full_name")
        if full_name_selector:
            name = row.locator(full_name_selector)
            if name.count() != 1:
                raise ChildIdentityMismatch("Result name is missing or ambiguous")
            if self.s.get("result_name_format") != "surname_first_patronymic":
                raise ChildIdentityMismatch("Result name format is not configured")
            return self._full_name_identity(name.inner_text())
        first = row.locator(self.s["result_first_name"])
        surname = row.locator(self.s["result_surname"])
        if first.count() != 1 or surname.count() != 1:
            raise ChildIdentityMismatch("Result first name or surname is missing or ambiguous")
        return first.inner_text(), surname.inner_text()

    def authenticated(self) -> bool:
        try:
            if self.s.get("navigation_mode") == "conclusions_list":
                indicators = self.page.locator(self.s["auth_indicator"])
                if not any(indicators.nth(i).is_visible() for i in range(indicators.count())):
                    return False
                self.page.locator(self.s["list_table"]).wait_for(state="visible", timeout=1500)
            else:
                self.page.locator(self.s["search_input"]).wait_for(state="visible", timeout=1500)
            return True
        except PlaywrightTimeout:
            return False

    def find_child(self, child: ChildName) -> None:
        if self.s.get("navigation_mode") == "conclusions_list":
            self._find_child_in_journal(child)
            return
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
            first, surname = self._result_identity(row)
            if child.matches(first, surname):
                matches.append(row)
        if not matches:
            raise ChildNotFound("Child not found: no exact first name and surname match")
        if len(matches) > 1:
            raise MultipleChildrenFound(f"{len(matches)} exact same-name records; additional identification is required")
        selected = matches[0]
        if self.s.get("result_action"):
            action = selected.locator(self.s["result_action"])
            if action.count() != 1 or not action.get_attribute("href"):
                raise ChildIdentityMismatch("The selected child's eighth-cell IPR action is missing or ambiguous")
            self.selected_ipr_href = action.get_attribute("href")
        if self.s.get("result_open"):
            record = selected.locator(self.s["result_open"])
            if record.count() != 1:
                raise ChildIdentityMismatch("The selected child's record link is missing or ambiguous")
            record.click()
        else:
            selected.click()

    def _journal_url(self, href: str, expected_path: str) -> str:
        target = urljoin(self.page.url, href)
        parsed = urlparse(target)
        if (parsed.scheme != "https" or parsed.hostname != "ircenter.gov.ua" or
                parsed.port not in (None, 443) or parsed.username or parsed.password or
                not parsed.path.startswith(expected_path)):
            raise ChildIdentityMismatch("Journal link points outside the expected IR Center page")
        return target

    def _find_child_in_journal(self, child: ChildName) -> None:
        matches: list[tuple[str, str]] = []
        visited: set[str] = set()
        self.selected_ipr_href = None
        for _ in range(100):
            if self.page.url in visited:
                raise ChildIdentityMismatch("Conclusions journal pagination loops")
            visited.add(self.page.url)
            self.page.locator(self.s["list_table"]).wait_for(state="visible", timeout=self.timeout_ms)
            rows = self.page.locator(self.s["result_rows"])
            for i in range(rows.count()):
                row = rows.nth(i)
                first, surname = self._result_identity(row)
                if child.matches(first, surname):
                    record = row.locator(self.s["result_open"])
                    action = row.locator(self.s["result_action"])
                    if record.count() != 1 or action.count() != 1:
                        raise ChildIdentityMismatch("Matching journal row has ambiguous record or IPR links")
                    record_href = record.get_attribute("href")
                    action_href = action.get_attribute("href")
                    if not record_href or not action_href:
                        raise ChildIdentityMismatch("Matching journal row is missing a record or IPR link")
                    matches.append((record_href, action_href))
                    if len(matches) > 1:
                        raise MultipleChildrenFound("Multiple exact first name and surname matches in the journal")
            next_page = self.page.locator(self.s["next_results_page"])
            available = [next_page.nth(i) for i in range(next_page.count())
                         if next_page.nth(i).is_visible() and next_page.nth(i).is_enabled()]
            if not available:
                break
            if len(available) != 1:
                raise ChildIdentityMismatch("Journal next-page link is ambiguous")
            href = available[0].get_attribute("href")
            if not href:
                raise ChildIdentityMismatch("Journal next-page link is missing its URL")
            target = self._journal_url(href, "/irc/index/conclusions-school")
            if target in visited:
                raise ChildIdentityMismatch("Conclusions journal pagination loops")
            self.page.goto(target, wait_until="domcontentloaded", timeout=self.timeout_ms)
        else:
            raise ChildIdentityMismatch("Conclusions journal exceeds the 100-page safety limit")
        if not matches:
            raise ChildNotFound("Child not found: no exact first name and surname match")
        record_href, action_href = matches[0]
        self._journal_url(record_href, "/irc/index/bid-view/bid_id/")
        target = self._journal_url(action_href, "/irc/index/conclusion-iprs/conclusion_id/")
        if not re.fullmatch(r"/irc/index/conclusion-iprs/conclusion_id/\d+", urlparse(target).path):
            raise ChildIdentityMismatch("IPR link has an unexpected route")
        self.selected_ipr_href = action_href
        self.page.goto(target, wait_until="domcontentloaded", timeout=self.timeout_ms)

    def verify_child_identity(self, child: ChildName, *, on_form: bool = False) -> None:
        if on_form and self.s.get("form_child_full_name"):
            name = self.page.locator(self.s["form_child_full_name"])
            if name.count() != 1 or self.s.get("form_child_name_format") != "surname_first_patronymic":
                raise ChildIdentityMismatch("IPR form child name is missing or ambiguous")
            full_name = labeled_school_full_name(name.inner_text())
            if full_name is None:
                raise ChildIdentityMismatch("IPR form child name label changed")
            first, surname = self._full_name_identity(full_name)
            if not child.matches(first, surname):
                raise ChildIdentityMismatch("IPR form does not belong to the requested child")
            return
        if not on_form and self.s.get("record_full_name"):
            name = self.page.locator(self.s["record_full_name"])
            if name.count() != 1 or self.s.get("record_name_format") != "surname_first_patronymic":
                raise ChildIdentityMismatch("IPR page child name is missing or ambiguous")
            first, surname = self._full_name_identity(name.inner_text())
            if not child.matches(first, surname):
                raise ChildIdentityMismatch("Opened IPR page does not belong to the requested child")
            return
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
        if self.s.get("navigation_mode") == "conclusions_list":
            top = self.page.locator(self.s["add_form_button"])
            row = self.page.locator(self.s.get("ipr_row_add_button", "table.zebra-stripe.list tr:has(td) td:nth-child(5) a.with-icon[href^='/irc/index/filling-ipr/ipr_id/']:has(img[src$='/add.png'])"))
            candidates = [(top.nth(i), "top") for i in range(top.count()) if top.nth(i).is_visible() and top.nth(i).is_enabled()]
            candidates += [(row.nth(i), "row") for i in range(row.count()) if row.nth(i).is_visible() and row.nth(i).is_enabled()]
            if len(candidates) != 1:
                raise FormButtonNotFound("Expected exactly one visible create IPR action")
            button, kind = candidates[0]
            expected = re.fullmatch(r"/irc/index/conclusion-iprs/conclusion_id/(\d+)", urlparse(self.page.url).path)
            href = button.get_attribute("href")
            if not href:
                raise FormButtonNotFound("Create IPR action has no destination")
            target = urlparse(urljoin(self.page.url, href))
            pattern = (r"/irc/index/filling-ipr/conclusion_id/(\d+)" if kind == "top" else
                       r"/irc/index/filling-ipr/ipr_id/\d+/conclusion_id/(\d+)")
            actual = re.fullmatch(pattern, target.path)
            if (not expected or target.scheme != "https" or target.hostname != "ircenter.gov.ua" or
                    target.port not in (None, 443) or target.username or target.password or
                    not actual or expected.group(1) != actual.group(1)):
                raise FormButtonNotFound("Create IPR link does not match the confirmed conclusion")
        else:
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
            if self.s.get("navigation_mode") == "conclusions_list":
                selected_path = urlparse(urljoin(self.page.url, self.selected_ipr_href or "")).path
                selected = re.fullmatch(r"/irc/index/conclusion-iprs/conclusion_id/(\d+)", selected_path)
                opened = re.fullmatch(r"/irc/index/filling-ipr/(?:ipr_id/\d+/)?conclusion_id/(\d+)", urlparse(self.page.url).path)
                if not selected or not opened or selected.group(1) != opened.group(1):
                    raise FormNotOpened("Opened IPR form does not match the selected conclusion")
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
