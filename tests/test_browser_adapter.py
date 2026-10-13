import shutil
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import sync_playwright

from ircenter_automation.errors import (
    ChildIdentityMismatch, ChildNotFound, FieldNotFound, FormButtonNotFound, MultipleChildrenFound,
    SubmissionNotConfirmed, VerificationError,
)
from ircenter_automation.form_filler import FormFiller
from ircenter_automation.ircenter import IRCenter
from ircenter_automation.mapping import FieldSpec, FieldValue
from ircenter_automation.normalization import ChildName


SELECTORS = {
    "search_input": "#search", "search_button": "#search-button", "result_rows": ".result",
    "no_results": "#none", "next_results_page": "#next", "result_first_name": ".first",
    "result_surname": ".surname", "record_first_name": "#record-first",
    "record_surname": "#record-surname", "add_form_button": "#add",
    "form_root": "#form", "form_heading": "#form h1", "form_heading_text": "New form",
    "form_child_first_name": "#form-first", "form_child_surname": "#form-surname",
    "submit_button": "#save", "success_indicator": "#success", "validation_error": ".validation-error",
}


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        executable = playwright.chromium.executable_path
        if not __import__("os").path.exists(executable):
            executable = shutil.which("chromium")
        if not executable:
            pytest.skip("Chromium is not installed")
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page()
        page.set_content("""
            <input id="search"><button id="search-button">Search</button>
            <div class="result" onclick="document.querySelector('#record').hidden=false">
              <span class="first">Іван</span><span class="surname">Шевченко</span>
            </div>
            <div id="none" hidden>No results</div>
            <button id="next" hidden>Next</button>
            <section id="record" hidden>
              <span id="record-first">Іван</span><span id="record-surname">Шевченко</span>
              <button id="add" onclick="document.querySelector('#form').hidden=false">Add</button>
            </section>
            <section id="form" hidden>
              <h1>New form</h1><span id="form-first">Іван</span>
              <span id="form-surname">Шевченко</span>
              <input id="birth" type="date"><textarea id="notes"></textarea>
              <select id="choice"><option value="">Choose</option><option value="yes">Yes</option></select>
              <input id="consent" type="checkbox">
              <button id="save" onclick="document.querySelector('#success').hidden=false">Save</button>
            </section>
            <p id="success" hidden>Saved form</p>
        """)
        yield page
        browser.close()


def _field(key, selector, control, expected, options=None):
    spec = FieldSpec(key, key, selector, control, True, options or {}, None, None, "input")
    return FieldValue(spec, expected)


def test_exact_navigation_fill_verify_and_confirm(page):
    child = ChildName("Іван", "Шевченко")
    site = IRCenter(page, SELECTORS, 1000)
    assert site.authenticated()
    site.find_child(child)
    site.verify_child_identity(child)
    site.open_new_form()
    site.verify_form_open(child)
    fields = (
        _field("birth", "#birth", "date", "2015-02-01"),
        _field("notes", "#notes", "textarea", "first\nsecond"),
        _field("choice", "#choice", "select", "Так", {"Так": "yes"}),
        _field("consent", "#consent", "checkbox", "true"),
    )
    filler = FormFiller(page)
    for field in fields:
        filler.fill(field)
    assert len(filler.verify_all(fields)) == 4
    site.check_validation_errors()
    site.submit_once()
    site.verify_submission()
    with pytest.raises(VerificationError):
        site.submit_once()


def test_duplicate_child_and_paginated_result_stop(page):
    site = IRCenter(page, SELECTORS, 1000)
    page.locator(".result").evaluate("el => el.after(el.cloneNode(true))")
    with pytest.raises(MultipleChildrenFound):
        site.find_child(ChildName("Іван", "Шевченко"))
    page.locator(".result").last.evaluate("el => el.remove()")
    page.locator("#next").evaluate("el => el.hidden = false")
    with pytest.raises(MultipleChildrenFound):
        site.find_child(ChildName("Іван", "Шевченко"))


def test_field_missing_and_full_readback_failure(page):
    page.locator("#form").evaluate("el => el.hidden = false")
    filler = FormFiller(page)
    with pytest.raises(FieldNotFound):
        filler.fill(_field("missing", "#missing", "text", "test"))
    field = _field("notes", "#notes", "textarea", "long text")
    filler.fill(field)
    page.locator("#notes").fill("long")
    with pytest.raises(VerificationError):
        filler.verify_all((field,))


def test_ambiguous_submission_response_does_not_retry(page):
    page.locator("#form").evaluate("el => el.hidden = false")
    page.locator("#save").evaluate("el => el.onclick = null")
    site = IRCenter(page, SELECTORS, 200)
    site.submit_once()
    with pytest.raises(SubmissionNotConfirmed):
        site.verify_submission()


def test_authentication_missing_child_not_found_and_identity_change(page):
    site = IRCenter(page, SELECTORS, 200)
    page.locator("#search").evaluate("el => el.hidden = true")
    assert not site.authenticated()
    page.locator("#search").evaluate("el => el.hidden = false")
    with pytest.raises(ChildNotFound):
        site.find_child(ChildName("Марія", "Шевченко"))
    site.find_child(ChildName("Іван", "Шевченко"))
    page.locator("#record-surname").evaluate("el => el.textContent = 'Іваненко'")
    with pytest.raises(ChildIdentityMismatch):
        site.verify_child_identity(ChildName("Іван", "Шевченко"))


def test_form_validation_error_blocks_submission(page):
    page.locator("#form").evaluate("el => el.hidden = false")
    page.locator("#form").evaluate("el => el.insertAdjacentHTML('beforeend', '<p class=validation-error>Invalid</p>')")
    with pytest.raises(VerificationError):
        IRCenter(page, SELECTORS, 200).check_validation_errors()


def test_list_full_name_and_eighth_cell_action_are_scoped_to_exact_row(page):
    page.set_content("""
        <input id="search"><button id="search-button">Search</button>
        <table class="zebra-stripe list"><tbody>
          <tr><td>1</td><td><a href="#other">Петренко Іван Петрович</a></td>
            <td></td><td></td><td></td><td></td><td></td>
            <td><a class="with-icon" href="/ipr/other"><img src="/add.png"></a></td><td></td><td></td></tr>
          <tr><td>2</td><td><a href="#record">Шевченко Іван Петрович</a></td>
            <td></td><td></td><td></td><td></td><td></td>
            <td><a class="with-icon" href="/ipr/expected"><img src="/page_white_text.png"></a></td><td></td><td></td></tr>
        </tbody></table>
        <div id="none" hidden></div><a id="next" hidden>Next</a>
    """)
    selectors = {**SELECTORS, "result_rows": "table.zebra-stripe.list tr:has(td)",
                 "result_full_name": "td:nth-child(2) a", "result_name_format": "surname_first_patronymic",
                 "result_open": "td:nth-child(2) a", "result_action": "td:nth-child(8) a.with-icon"}
    site = IRCenter(page, selectors, 1000)
    site.find_child(ChildName("Іван", "Шевченко"))
    assert site.selected_ipr_href == "/ipr/expected"
    assert page.url.endswith("#record")


def test_list_name_that_cannot_be_parsed_stops(page):
    page.set_content("""
        <input id="search"><button id="search-button">Search</button>
        <table class="zebra-stripe list"><tr><td>1</td>
        <td><a href="#record">Шевченко Іван</a></td>
        <td></td><td></td><td></td><td></td><td></td>
        <td><a class="with-icon" href="/ipr/expected">IPR</a></td><td></td><td></td></tr></table>
        <div id="none" hidden></div><a id="next" hidden>Next</a>
    """)
    selectors = {**SELECTORS, "result_rows": "table.zebra-stripe.list tr:has(td)",
                 "result_full_name": "td:nth-child(2) a", "result_name_format": "surname_first_patronymic",
                 "result_open": "td:nth-child(2) a", "result_action": "td:nth-child(8) a.with-icon"}
    with pytest.raises(ChildIdentityMismatch):
        IRCenter(page, selectors, 1000).find_child(ChildName("Іван", "Шевченко"))


JOURNAL_SELECTORS = {
    **SELECTORS, "navigation_mode": "conclusions_list", "auth_indicator": "a[href='/logout']",
    "list_table": "table.zebra-stripe.list", "result_rows": "table.zebra-stripe.list tr:has(td)",
    "next_results_page": "#pagination-digg a:has-text('Далі')",
    "result_full_name": "td:nth-child(2) a", "result_name_format": "surname_first_patronymic",
    "result_open": "td:nth-child(2) a", "result_action": "td:nth-child(8) a.with-icon",
    "record_full_name": "table.zebra-stripe.list tr:has(td:first-child:text-is(\"Прізвище, ім'я, по батькові дитини\")) td:nth-child(2)",
    "record_name_format": "surname_first_patronymic",
    "add_form_button": "a.add-link.with-icon[href^='/irc/index/filling-ipr/conclusion_id/']",
    "ipr_row_add_button": "table.zebra-stripe.list tr:has(td) td:nth-child(5) a.with-icon[href^='/irc/index/filling-ipr/ipr_id/']:has(img[src$='/add.png'])",
}


def _journal_row(name: str, number: int) -> str:
    return (f'<tr><td>1</td><td><a href="/irc/index/bid-view/bid_id/{number}">{name}</a></td>'
            '<td></td><td></td><td></td><td></td><td></td>'
            f'<td><a class="with-icon" href="/irc/index/conclusion-iprs/conclusion_id/{number}">IPR</a></td>'
            '<td></td><td></td></tr>')


def _journal_html(rows: str, next_href: str | None = None) -> str:
    next_link = f'<div id="pagination-digg"><a href="{next_href}">Далі →</a></div>' if next_href else ''
    return ('<a href="/logout">Вийти</a><table class="zebra-stripe list"><tbody>' + rows +
            '</tbody></table>' + next_link)


def _route_journal(page, first: str, second: str, ipr_actions: str | None = None):
    def handle(route):
        parsed = urlparse(route.request.url)
        if parsed.path == "/irc/index/conclusions-school":
            body = second if parse_qs(parsed.query).get("page") == ["2"] else first
        elif parsed.path == "/irc/index/conclusion-iprs/conclusion_id/42":
            body = ("<table class='zebra-stripe list'><tr><td>Прізвище, ім'я, по батькові дитини</td>"
                    "<td>Шевченко Іван Петрович</td></tr></table>"
                    + (ipr_actions if ipr_actions is not None else
                       "<a class='add-link with-icon' href='/irc/index/filling-ipr/conclusion_id/42'>Створити ІПР</a>"))
        elif parsed.path in ("/irc/index/filling-ipr/conclusion_id/42",
                             "/irc/index/filling-ipr/ipr_id/99/conclusion_id/42"):
            body = "<form id='iprForm'></form>"
        else:
            route.abort()
            return
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
    page.route("https://ircenter.gov.ua/**", handle)
    page.goto("https://ircenter.gov.ua/irc/index/conclusions-school")


def test_journal_scans_all_pages_then_opens_confirmed_ipr(page):
    first = _journal_html(_journal_row("Петренко Іван Петрович", 10), "?page=2")
    second = _journal_html(_journal_row("Шевченко Іван Петрович", 42))
    _route_journal(page, first, second)
    site = IRCenter(page, JOURNAL_SELECTORS, 1000)
    child = ChildName("Іван", "Шевченко")
    assert site.authenticated()
    site.find_child(child)
    assert page.url.endswith("/conclusion-iprs/conclusion_id/42")
    site.verify_child_identity(child)
    site.open_new_form()
    assert page.url.endswith("/filling-ipr/conclusion_id/42")


def _ipr_plus_row(ipr_id: int, conclusion_id: int = 42) -> str:
    return ("<tr><td>date</td><td>school</td><td>period</td><td>protocol</td><td>"
            f"<a class='with-icon' href='/irc/index/filling-ipr/ipr_id/{ipr_id}/conclusion_id/{conclusion_id}'>"
            "<img src='/images/ico/add.png' alt='Створити IПР'></a></td><td>actions</td></tr>")


def test_ipr_row_plus_opens_matching_form(page):
    rows = (_ipr_plus_row(99) +
            "<tr><td>older</td><td>school</td><td>period</td><td>protocol</td>"
            "<td><a class='with-icon' href='/irc/index/get-ipr-file/ipr_id/98/conclusion_id/42'>"
            "<img src='/images/ico/doc_pdf.png' alt='Завантажити IПР'></a></td><td></td></tr>")
    actions = f"<table class='zebra-stripe list'><tbody>{rows}</tbody></table>"
    _route_journal(page, _journal_html(_journal_row("Шевченко Іван Петрович", 42)), "", actions)
    site = IRCenter(page, JOURNAL_SELECTORS, 1000)
    child = ChildName("Іван", "Шевченко")
    site.find_child(child)
    site.verify_child_identity(child)
    site.open_new_form()
    assert page.url.endswith("/filling-ipr/ipr_id/99/conclusion_id/42")


@pytest.mark.parametrize("actions", [
    "<table class='zebra-stripe list'>" + _ipr_plus_row(99) + _ipr_plus_row(100) + "</table>",
    "<table class='zebra-stripe list'>" + _ipr_plus_row(99, 43) + "</table>",
    "<a class='add-link with-icon' href='/irc/index/filling-ipr/conclusion_id/42'>Створити ІПР</a>"
    + "<table class='zebra-stripe list'>" + _ipr_plus_row(99) + "</table>",
])
def test_ipr_row_plus_ambiguous_or_wrong_conclusion_stops(page, actions):
    _route_journal(page, _journal_html(_journal_row("Шевченко Іван Петрович", 42)), "", actions)
    site = IRCenter(page, JOURNAL_SELECTORS, 1000)
    site.find_child(ChildName("Іван", "Шевченко"))
    with pytest.raises(FormButtonNotFound):
        site.open_new_form()
    assert page.url.endswith("/conclusion-iprs/conclusion_id/42")


def test_ipr_page_identity_and_create_link_must_match(page):
    _route_journal(page, _journal_html(_journal_row("Шевченко Іван Петрович", 42)), "")
    site = IRCenter(page, JOURNAL_SELECTORS, 1000)
    child = ChildName("Іван", "Шевченко")
    site.find_child(child)
    page.locator("table.zebra-stripe.list td:nth-child(2)").evaluate("el => el.textContent = 'Петренко Іван Петрович'")
    with pytest.raises(ChildIdentityMismatch):
        site.verify_child_identity(child)
    page.locator("table.zebra-stripe.list td:nth-child(2)").evaluate("el => el.textContent = 'Шевченко Іван Петрович'")
    page.locator("a.add-link.with-icon").evaluate(
        "el => el.href = '/irc/index/filling-ipr/conclusion_id/43'")
    with pytest.raises(FormButtonNotFound):
        site.open_new_form()


@pytest.mark.parametrize("separator", ["", " "])
def test_ipr_form_identity_parses_labeled_full_name(page, separator):
    page.set_content(
        f"<form id='iprForm'><p>прізвище, власне ім’я, по батькові{separator}(за наявності) "
        "Шевченко Іван Петрович</p></form>"
    )
    selectors = {**JOURNAL_SELECTORS,
                 "form_child_full_name": "#iprForm p:has-text('прізвище, власне ім’я, по батькові')",
                 "form_child_name_format": "surname_first_patronymic"}
    IRCenter(page, selectors, 1000).verify_child_identity(ChildName("Іван", "Шевченко"), on_form=True)
    with pytest.raises(ChildIdentityMismatch):
        IRCenter(page, selectors, 1000).verify_child_identity(ChildName("Іван", "Петренко"), on_form=True)


def test_journal_duplicate_on_later_page_stops_before_open(page):
    first = _journal_html(_journal_row("Шевченко Іван Петрович", 42), "?page=2")
    second = _journal_html(_journal_row("Шевченко Іван Олександрович", 43))
    _route_journal(page, first, second)
    with pytest.raises(MultipleChildrenFound):
        IRCenter(page, JOURNAL_SELECTORS, 1000).find_child(ChildName("Іван", "Шевченко"))
    assert page.url.endswith("?page=2")


@pytest.mark.parametrize("next_href", ["?page=2", "https://evil.example/irc/index/conclusions-school"])
def test_journal_bad_pagination_stops(page, next_href):
    first = _journal_html(_journal_row("Шевченко Іван Петрович", 42), next_href)
    second = _journal_html(_journal_row("Петренко Олена Петрівна", 43), "?page=2")
    _route_journal(page, first, second)
    with pytest.raises(ChildIdentityMismatch):
        IRCenter(page, JOURNAL_SELECTORS, 1000).find_child(ChildName("Іван", "Шевченко"))
    assert "/conclusion-iprs/" not in page.url
