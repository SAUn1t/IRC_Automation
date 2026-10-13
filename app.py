import shutil
import sys
import json
import secrets
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ircenter_automation.config_migration import upgrade_example_config
from ircenter_automation.gui.main_window import MainWindow


def ensure_extension_token(settings_path: Path) -> None:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if not settings.get("extension_token"):
        settings["extension_token"] = secrets.token_urlsafe(32)
        temporary = settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(settings_path)


def main() -> int:
    config_dir = Path.home() / ".ircenter-automation"
    config_dir.mkdir(parents=True, exist_ok=True)
    examples = Path(__file__).resolve().parent / "config"
    for name in ("settings", "field_mapping"):
        target = config_dir / f"{name}.json"
        if not target.exists():
            shutil.copyfile(examples / f"{name}.example.json", target)
    upgrade_example_config(config_dir, examples)
    settings_path = config_dir / "settings.json"
    ensure_extension_token(settings_path)
    app = QApplication(sys.argv)
    window = MainWindow(settings_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
