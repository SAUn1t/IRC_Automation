import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect, sync_playwright


def test_extension_navigates_paged_journal_and_fills_only_four_fields(tmp_path: Path):
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
    extension_state = {"value": {"job": job, "stage": "journal", "tabId": 42}}

    def row(name: str, number: int) -> str:
        return (f"<tr><td>1</td><td><a href='/irc/index/bid-view/bid_id/{number}'>{name}</a></td>"
                "<td></td><td></td><td></td><td></td><td></td>"
                f"<td><a href='/irc/index/conclusion-iprs/conclusion_id/{number}'>ІПР</a></td>"
                "<td></td><td></td></tr>")

    def route_handler(route):
        url = urlparse(route.request.url)
        if url.path == "/irc/index/conclusions-school":
            second = parse_qs(url.query).get("page") == ["2"]
            rows = row("Шевченко Іван Петрович", 42) if second else row("Петренко Іван Петрович", 10)
            next_link = "" if second else "<div id='pagination-digg'><a href='?page=2'>Далі →</a></div>"
            body = f"<table class='zebra-stripe list'>{rows}</table>{next_link}"
        elif url.path == "/irc/index/conclusion-iprs/conclusion_id/42":
            body = ("<table class='zebra-stripe list'>"
                    "<tr><td>Прізвище, ім'я, по батькові дитини</td><td>Шевченко Іван Петрович</td></tr>"
                    "<tr><td>date</td><td>school</td><td>period</td><td>protocol</td><td>"
                    "<a class='with-icon' href='/irc/index/filling-ipr/ipr_id/99/conclusion_id/42'>"
                    "<img src='/images/ico/add.png'></a></td><td></td></tr></table>")
        elif url.path == "/irc/index/filling-ipr/ipr_id/99/conclusion_id/42":
            body = ("<div id='content-wrapper'><div class='nosidebar'>"
                    "<h1>Створення індивідуальної програми розвитку учня закладу загальної середньої освіти</h1>"
                    "<form id='iprForm'>"
                    "<p>прізвище, власне ім’я, по батькові(за наявності) Шевченко Іван Петрович</p>"
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
            "window.chrome.runtime = {sendMessage: message => window.testBridge(message)}; "
            "window.addEventListener('DOMContentLoaded', () => {" + content + "}, {once: true});"
        )
        page = context.new_page()
        page.goto("https://ircenter.gov.ua/irc/index/conclusions-school")
        page.wait_for_url("**/irc/index/filling-ipr/ipr_id/99/conclusion_id/42", timeout=10000)
        expect(page.locator("[name='execution_period']")).to_have_value(job["fields"][0]["value"])
        expect(page.locator("[name='year_of_study']")).to_have_value("2")
        expect(page.locator("[name='child_grade']")).to_have_value("2-А")
        expect(page.locator("[name='parents_phones']")).to_have_value("000 000 000")
        assert [message["type"] for message in messages].count("claim") == 0
        assert any(message["type"] == "status" and message["status"] == "ready" for message in messages)
        context.close()
