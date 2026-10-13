import json
from pathlib import Path


def _write_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def upgrade_example_config(config_dir: Path, examples_dir: Path) -> bool:
    """Upgrade only untouched selector and mapping placeholders from older releases."""
    settings_path = config_dir / "settings.json"
    mapping_path = config_dir / "field_mapping.json"
    try:
        old_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        old_mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        current_settings = json.loads((examples_dir / "settings.example.json").read_text(encoding="utf-8"))
        current_mapping = json.loads((examples_dir / "field_mapping.example.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(old_settings, dict) or not isinstance(old_mapping, dict):
        return False
    selectors = old_settings.get("selectors", {})
    if not isinstance(selectors, dict):
        return False
    old_placeholders = (
        old_settings.get("website_url") == "https://ircenter.gov.ua/"
        and selectors.get("search_input") == "REPLACE_AFTER_DOM_INSPECTION"
        and selectors.get("search_button") == "REPLACE_AFTER_DOM_INSPECTION"
        and selectors.get("record_first_name") == "REPLACE_AFTER_DOM_INSPECTION"
        and selectors.get("form_root") == "REPLACE_AFTER_DOM_INSPECTION"
        and "manual_review_only" not in old_settings
    )
    fields = old_mapping.get("fields")
    old_mapping_placeholder = (
        isinstance(fields, list) and len(fields) == 2 and all(isinstance(field, dict) for field in fields)
        and {field.get("key") for field in old_mapping["fields"]} == {"date_of_birth", "notes"}
        and all(field.get("selector") == "REPLACE_AFTER_DOM_INSPECTION" for field in old_mapping["fields"])
    )
    if not old_placeholders or not old_mapping_placeholder:
        if (selectors.get("navigation_mode") == "conclusions_list"
                and "ipr_row_add_button" not in selectors
                and selectors.get("add_form_button") == current_settings["selectors"]["add_form_button"]):
            selectors["ipr_row_add_button"] = current_settings["selectors"]["ipr_row_add_button"]
            _write_json(settings_path, old_settings)
            return True
        return False
    old_settings["website_url"] = current_settings["website_url"]
    old_settings["manual_review_only"] = True
    old_settings["selectors"] = current_settings["selectors"]
    _write_json(mapping_path, current_mapping)
    _write_json(settings_path, old_settings)
    return True
