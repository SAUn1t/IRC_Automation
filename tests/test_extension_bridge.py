import json
import socket
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import ircenter_automation.extension_bridge as bridge_module
from ircenter_automation.extension_bridge import ExtensionBridge
from ircenter_automation.manual_entry import ManualEntryGuide, ManualField


def test_bridge_delivers_one_authorized_job_and_receives_status(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        monkeypatch.setattr(bridge_module, "PORT", sock.getsockname()[1])
    guide = ManualEntryGuide("Іван Шевченко", "synthetic.docx", (
        ManualField("Рік навчання", "year_of_study", "2"),
    ))
    token = "test-token-with-enough-characters"
    with ExtensionBridge(token, guide) as bridge:
        base = f"http://127.0.0.1:{bridge_module.PORT}"
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(base + "/job", timeout=2)
        assert unauthorized.value.code == 403
        headers = {"Authorization": f"Bearer {token}"}
        with pytest.raises(HTTPError) as outdated:
            urlopen(Request(base + "/job", headers=headers), timeout=2)
        assert outdated.value.code == 409
        assert bridge.next_status() == (
            "error", "Chrome extension is outdated. Load it from the installed app folder."
        )
        headers["X-IRCenter-Extension-Version"] = "1.3.1"
        def read(path):
            with urlopen(Request(base + path, headers=headers), timeout=2) as response:
                return json.load(response)
        job = read("/job")["job"]
        assert job["child"] == {"first": "Іван", "surname": "Шевченко"}
        assert job["fields"] == [{"name": "year_of_study", "value": "2"}]
        assert read("/job")["job"] is None
        assert read(f"/alive?id={bridge.job_id}") == {"active": True}
        assert read("/version") == {"extensionVersion": "1.3.1"}
        request = Request(base + "/status", data=json.dumps({
            "id": bridge.job_id, "type": "ready", "detail": "Four fields filled",
        }).encode(), headers={**headers, "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=2) as response:
            assert json.load(response) == {"ok": True}
        assert bridge.next_status() == ("ready", "Four fields filled")
