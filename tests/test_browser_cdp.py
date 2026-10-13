import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from ircenter_automation.browser import BrowserSession
from ircenter_automation.settings import load_settings


def test_normal_browser_mode_attaches_to_visible_browser_profile(tmp_path: Path):
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not chromium:
        pytest.skip("No installed Chrome-compatible browser")
    wrapper = tmp_path / "test-chromium"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{chromium}" --no-sandbox --disable-dev-shm-usage "$@"\n', encoding="utf-8"
    )
    wrapper.chmod(0o700)
    settings = load_settings(Path("config/settings.example.json"))
    settings = replace(
        settings, website_url="about:blank", browser="chrome", browser_transport="cdp",
        browser_executable=wrapper, browser_profile=tmp_path / "profile",
        browser_headless=True, timeout_ms=15000,
    )
    with BrowserSession(settings) as session:
        assert session.context is not None
        assert session.page is not None
        assert session.browser_process is not None
        session.page.set_content("<p id='attached'>Connected</p>")
        assert session.page.locator("#attached").inner_text() == "Connected"
    assert session.browser_process is None
