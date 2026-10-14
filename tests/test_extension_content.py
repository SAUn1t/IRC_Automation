import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.mark.parametrize("row_label", ["Доступність", "Невірний підпис"])
def test_current_ipr_form_fills_matching_table_rows_and_choices(tmp_path: Path, row_label: str):
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    url = "https://ircenter.gov.ua/irc/index/filling-ipr/conclusion_id/42"
    fields = [
        {"name": "execution_period", "value": "з 01.09.2026 по 31.05.2027", "kind": "text"},
        {"name": "year_of_study", "value": "2", "kind": "select"},
        {"name": "child_grade", "value": "2-А", "kind": "text"},
        {"name": "parents_phones", "value": "000 000 000", "kind": "text"},
        {"name": "5[1][1]", "value": "Тихий кабінет", "kind": "textarea", "rowLabel": row_label},
        {"name": "5[26][1]", "value": "0", "kind": "radio"},
        {"name": "5[29][1]", "value": "Математика", "kind": "textarea"},
        {"name": "5[30][1]", "value": "Читання", "kind": "textarea"},
        {"name": "6[1][1]", "value": "Мовна галузь", "kind": "textarea"},
        {"name": "8[7][1]", "value": "false", "kind": "checkbox"},
        {"name": "8[9][0]", "value": "false", "kind": "checkbox"},
    ]
    state = {"job": {"id": "synthetic-job", "child": {"first": "Іван", "surname": "Шевченко"},
                     "fields": fields}, "stage": "form", "formUrl": url}
    messages = []
    html = """<div id='content-wrapper'><div class='nosidebar'>
    <h1>Створення індивідуальної програми розвитку учня закладу загальної середньої освіти</h1>
    <form id='iprForm'>
    <p>прізвище, власне ім’я, по батькові (за наявності) Шевченко Іван Петрович</p>
    <input name='execution_period'><select name='year_of_study'><option>1</option><option>2</option></select>
    <input name='child_grade'><input name='parents_phones'>
    <table><tr><td>Доступність</td><td><textarea name='5[1][1]'></textarea></td></tr></table>
    <input type='radio' name='5[26][1]' value='1' checked>
    <input type='radio' name='5[26][1]' value='0'>
    <table id='sec529table'><tr class='sec529tr'><td><textarea name='5[29][1]'></textarea></td></tr></table>
    <a href='javascript: addSection5Row29();'>Додати предмет</a>
    <table id='sec61table'><tr class='sec61tr'><td><textarea name='6[1][1]'></textarea></td></tr></table>
    <a href='javascript: addSection6Row1();'>Додати напрям</a>
    <input type='checkbox' name='8[7][1]' checked>
    <input type='checkbox' name='8[9][0]' checked>
    </form></div></div>
    <script>function addSection5Row29() { document.querySelector('#sec529table').insertAdjacentHTML(
      'beforeend', '<tr class="sec529tr"><td><textarea name="5[30][1]"></textarea></td></tr>'); }
    </script>"""
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"), executable_path=chromium, headless=True)
        context.route(url, lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))

        def reply(_source, message):
            messages.append(message)
            if message["type"] == "getState":
                return {"state": state}
            if message["type"] == "alive":
                return {"active": True}
            return {"ok": True}

        context.expose_binding("testBridge", reply)
        content = Path("chrome_extension/content.js").read_text(encoding="utf-8")
        context.add_init_script(
            "window.chrome = {runtime: {sendMessage: message => window.testBridge(message), "
            "onMessage: {addListener: () => {}}}}; "
            "window.addEventListener('DOMContentLoaded', () => {" + content + "}, {once: true});")
        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(300)
        if row_label != "Доступність":
            assert any(message.get("status") == "error" and "row label changed" in message.get("detail", "")
                       for message in messages)
            expect(page.locator("[name='execution_period']")).to_have_value("")
            context.close()
            return
        assert not any(message.get("status") == "error" for message in messages), messages
        expect(page.locator("[name='5[30][1]']")).to_have_value("Читання")
        expect(page.locator("[name='5[1][1]']")).to_have_value("Тихий кабінет")
        expect(page.locator("[name='5[26][1]'][value='0']")).to_be_checked()
        expect(page.locator("[name='8[7][1]']")).not_to_be_checked()
        expect(page.locator("[name='8[9][0]']")).not_to_be_checked()
        assert any(message.get("status") == "ready" for message in messages)
        context.close()


@pytest.mark.parametrize("start_at,next_href,duplicate,top_create", [
    (start_at, next_href, False, False)
    for start_at in ("journal", "journal-page-2", "ipr", "form")
    for next_href in ("?page=2", "/irc/index/conclusions-school/page/2")
] + [("journal", "?page=2", True, False), ("ipr", "?page=2", False, True)])
def test_extension_navigates_from_supported_page_and_fills_only_four_fields(
    tmp_path: Path, start_at: str, next_href: str, duplicate: bool, top_create: bool,
):
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    job = {"id": "synthetic-job", "child": {"first": "Іван", "surname": "Шевченко"}, "fields": [
        {"name": "execution_period", "value": "з 01.09.2026 по 31.05.2027"},
        {"name": "year_of_study", "value": "2"},
        {"name": "child_grade", "value": "2-А"},
        {"name": "parents_phones", "value": "000 000 000"},
    ]}
    messages = []
    page_two_requests = []
    ipr_url = "https://ircenter.gov.ua/irc/index/conclusion-iprs/conclusion_id/42"
    form_url = ("https://ircenter.gov.ua/irc/index/filling-ipr/conclusion_id/42" if start_at == "form" or top_create
                else "https://ircenter.gov.ua/irc/index/filling-ipr/ipr_id/99/conclusion_id/42")
    initial = {"job": job, "stage": "journal" if start_at == "journal-page-2" else start_at, "tabId": 42}
    if start_at == "ipr":
        initial["conclusionUrl"] = ipr_url
    if start_at == "form":
        initial["formUrl"] = form_url
    extension_state = {"value": initial}

    def row(name: str, number: int) -> str:
        return (f"<tr><td>1</td><td><a href='/irc/index/bid-view/bid_id/{number}'>{name}</a></td>"
                "<td></td><td></td><td></td><td></td><td></td>"
                f"<td><a href='/irc/index/conclusion-iprs/conclusion_id/{number}'>ІПР</a></td>"
                "<td></td><td></td></tr>")

    def route_handler(route):
        url = urlparse(route.request.url)
        if url.path in ("/irc/index/conclusions-school", "/irc/index/conclusions-school/page/2"):
            second = parse_qs(url.query).get("page") == ["2"] or url.path.endswith("/page/2")
            if second:
                page_two_requests.append(route.request.resource_type)
                if route.request.resource_type == "fetch":
                    route.fulfill(status=403, body="Background requests are blocked")
                    return
            rows = row("Шевченко Іван Петрович", 42) if second else row(
                "Шевченко Іван Петрович" if duplicate else "Петренко Іван Петрович", 10,
            )
            next_link = "" if second else f"<div id='pagination-digg'><a href='{next_href}'>Далі →</a></div>"
            body = f"<table class='zebra-stripe list'>{rows}</table>{next_link}"
        elif url.path == "/irc/index/conclusion-iprs/conclusion_id/42":
            body = ("<table class='zebra-stripe list'>"
                    "<tr><td>Прізвище, ім'я, по батькові дитини</td><td>Шевченко Іван Петрович</td></tr>"
                    "</table>"
                    + ("<a class='add-link with-icon' href='/irc/index/filling-ipr/conclusion_id/42'>"
                       "Створити ІПР</a>" if top_create else
                       "<table class='zebra-stripe list'><tr><td>date</td><td>school</td><td>period</td>"
                       "<td>protocol</td><td><a class='with-icon' "
                       "href='/irc/index/filling-ipr/ipr_id/99/conclusion_id/42'>"
                       "<img src='/images/ico/add.png'></a></td><td></td></tr></table>"))
        elif url.path in ("/irc/index/filling-ipr/ipr_id/99/conclusion_id/42",
                          "/irc/index/filling-ipr/conclusion_id/42"):
            body = ("<div id='content-wrapper'><div class='nosidebar'>"
                    "<h1>Створення індивідуальної програми розвитку учня закладу загальної середньої освіти</h1>"
                    "<form id='iprForm'>"
                    "<p>прізвище, власне ім’я, по батькові(за наявності) Шевченко Іван Петрович</p>"
                    "<p>прізвище, власне ім’я, по батькові (за наявності) батьків "
                    "(інших законних представників) учня Шевченко Олена Іванівна</p>"
                    "<input name='execution_period'><select name='year_of_study'>"
                    "<option value='1'>1</option><option value='2'>2</option></select>"
                    "<input name='child_grade'><input name='parents_phones'>"
                    "</form></div></div>")
        else:
            route.abort()
            return
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"), executable_path=chromium, headless=True,
        )
        context.route("https://ircenter.gov.ua/**", route_handler)

        def reply(_source, message):
            messages.append(message)
            if message["type"] == "getState":
                return {"state": extension_state["value"]}
            if message["type"] == "setState":
                extension_state["value"] = message["state"]
                return {"ok": True}
            if message["type"] == "clearState":
                extension_state["value"] = None
                return {"ok": True}
            if message["type"] == "alive":
                return {"active": True}
            return {"ok": True}

        context.expose_binding("testBridge", reply)
        content = Path("chrome_extension/content.js").read_text(encoding="utf-8")
        context.add_init_script(
            "window.chrome = window.chrome || {}; "
            "window.chrome.runtime = {sendMessage: message => window.testBridge(message).then(reply => {"
            "if (message.type === 'status' && message.status === 'error') window.__errorReported = true; "
            "return reply;}), "
            "onMessage: {addListener: () => {}}}; "
            "window.addEventListener('DOMContentLoaded', () => {" + content + "}, {once: true});"
        )
        page = context.new_page()
        page.goto({"journal": "https://ircenter.gov.ua/irc/index/conclusions-school",
                   "journal-page-2": "https://ircenter.gov.ua" + next_href.replace("?", "/irc/index/conclusions-school?", 1),
                   "ipr": ipr_url, "form": form_url}[start_at])
        if duplicate:
            page.wait_for_function("window.__errorReported === true")
            assert page.url.endswith("/irc/index/conclusions-school?page=2")
            assert any("exactly one child" in item.get("detail", "") for item in messages)
            assert not any(item.get("status") == "ready" for item in messages)
            context.close()
            return
        page.wait_for_url(form_url, timeout=10000)
        expect(page.locator("[name='execution_period']")).to_have_value(job["fields"][0]["value"])
        expect(page.locator("[name='year_of_study']")).to_have_value("2")
        expect(page.locator("[name='child_grade']")).to_have_value("2-А")
        expect(page.locator("[name='parents_phones']")).to_have_value("000 000 000")
        assert [message["type"] for message in messages].count("claim") == 0
        assert any(message["type"] == "status" and message["status"] == "ready" for message in messages)
        if start_at.startswith("journal"):
            assert page_two_requests and set(page_two_requests) == {"document"}
        context.close()


@pytest.mark.parametrize("start_at", ["ipr", "form"])
def test_open_page_for_other_child_restarts_at_journal_without_filling(tmp_path: Path, start_at: str):
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("Chromium is not installed")
    path = ("/irc/index/conclusion-iprs/conclusion_id/42" if start_at == "ipr"
            else "/irc/index/filling-ipr/ipr_id/99/conclusion_id/42")
    url = "https://ircenter.gov.ua" + path
    job = {"id": "synthetic-job", "child": {"first": "Іван", "surname": "Шевченко"}}
    state = {"job": job, "stage": start_at, "tabId": 42, "directEntry": True,
             "conclusionUrl" if start_at == "ipr" else "formUrl": url}
    messages = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"), executable_path=chromium, headless=True,
        )
        body = ("<table class='zebra-stripe list'><tr><td>Прізвище, ім'я, по батькові дитини</td>"
                "<td>Петренко Олена Петрівна</td></tr></table>" if start_at == "ipr" else
                "<div id='content-wrapper'><div class='nosidebar'>"
                "<h1>Створення індивідуальної програми розвитку учня закладу загальної середньої освіти</h1>"
                "<form id='iprForm'><p>прізвище, власне ім’я, по батькові(за наявності) "
                "Петренко Олена Петрівна</p><input name='execution_period'></form></div></div>")
        context.route(url, lambda route: route.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=body,
        ))

        def reply(_source, message):
            messages.append(message)
            if message["type"] == "getState":
                return {"state": state}
            if message["type"] == "alive":
                return {"active": True}
            return {"ok": True}

        context.expose_binding("testBridge", reply)
        content = Path("chrome_extension/content.js").read_text(encoding="utf-8")
        context.add_init_script(
            "window.chrome = window.chrome || {}; "
            "window.chrome.runtime = {sendMessage: message => {"
            "if (message.type === 'restartJournal') window.__restarted = true; "
            "return window.testBridge(message);}, onMessage: {addListener: () => {}}}; "
            "window.addEventListener('DOMContentLoaded', () => {" + content + "}, {once: true});"
        )
        page = context.new_page()
        page.goto(url)
        page.wait_for_function("window.__restarted === true")
        assert page.url == url
        assert any(message["type"] == "restartJournal" for message in messages)
        assert not any(message["type"] == "status" and message["status"] == "ready" for message in messages)
        context.close()
