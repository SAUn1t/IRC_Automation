import json
from pathlib import Path

from ircenter_automation.config_migration import upgrade_example_config


def test_upgrade_only_untouched_placeholders(tmp_path: Path):
    examples = Path("config")
    settings = {
        "website_url": "https://ircenter.gov.ua/",
        "docx_folder": "C:/ExampleDocs",
        "browser": "msedge",
        "selectors": {
            "search_input": "REPLACE_AFTER_DOM_INSPECTION",
            "search_button": "REPLACE_AFTER_DOM_INSPECTION",
            "record_first_name": "REPLACE_AFTER_DOM_INSPECTION",
            "form_root": "REPLACE_AFTER_DOM_INSPECTION",
        },
    }
    mapping = {"fields": [
        {"key": "date_of_birth", "selector": "REPLACE_AFTER_DOM_INSPECTION"},
        {"key": "notes", "selector": "REPLACE_AFTER_DOM_INSPECTION"},
    ]}
    settings_path = tmp_path / "settings.json"
    mapping_path = tmp_path / "field_mapping.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    assert upgrade_example_config(tmp_path, examples)
    upgraded = json.loads(settings_path.read_text(encoding="utf-8"))
    assert upgraded["docx_folder"] == "C:/ExampleDocs"
    assert upgraded["browser"] == "msedge"
    assert upgraded["manual_review_only"] is True
    assert upgraded["selectors"]["navigation_mode"] == "conclusions_list"
    assert len(json.loads(mapping_path.read_text(encoding="utf-8"))["fields"]) == 4
    assert not upgrade_example_config(tmp_path, examples)


def test_upgrade_preserves_custom_mapping(tmp_path: Path):
    settings = {"website_url": "https://ircenter.gov.ua/", "selectors": {
        "search_input": "REPLACE_AFTER_DOM_INSPECTION",
        "search_button": "REPLACE_AFTER_DOM_INSPECTION",
        "record_first_name": "REPLACE_AFTER_DOM_INSPECTION",
        "form_root": "REPLACE_AFTER_DOM_INSPECTION",
    }}
    mapping = {"fields": [{"key": "custom", "selector": "#custom"}]}
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (tmp_path / "field_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    assert not upgrade_example_config(tmp_path, Path("config"))
    assert json.loads((tmp_path / "field_mapping.json").read_text(encoding="utf-8")) == mapping
