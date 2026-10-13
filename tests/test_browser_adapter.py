import shutil

import pytest
from playwright.sync_api import sync_playwright

from ircenter_automation.errors import (
    ChildIdentityMismatch, ChildNotFound, FieldNotFound, MultipleChildrenFound,
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
