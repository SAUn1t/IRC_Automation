import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ircenter_automation.config_migration import upgrade_example_config
from ircenter_automation.gui.main_window import MainWindow


def main() -> int:
    config_dir = Path.home() / ".ircenter-automation"
    config_dir.mkdir(parents=True, exist_ok=True)
    examples = Path(__file__).resolve().parent / "config"
    for name in ("settings", "field_mapping"):
        target = config_dir / f"{name}.json"
        if not target.exists():
            shutil.copyfile(examples / f"{name}.example.json", target)
    upgrade_example_config(config_dir, examples)
    app = QApplication(sys.argv)
    window = MainWindow(config_dir / "settings.json")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
