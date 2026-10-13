import json

from app import ensure_extension_token


def test_pairing_token_is_created_once_for_existing_settings(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"browser": "chrome"}), encoding="utf-8")
    ensure_extension_token(settings_path)
    first = json.loads(settings_path.read_text(encoding="utf-8"))["extension_token"]
    assert len(first) >= 24
    ensure_extension_token(settings_path)
    assert json.loads(settings_path.read_text(encoding="utf-8"))["extension_token"] == first
