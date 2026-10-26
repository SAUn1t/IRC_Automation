import shutil
import sys
import json
import secrets
import os
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
    root = Path(__file__).resolve().parent
    installed_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else root
    if getattr(sys, "frozen", False):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(installed_root / "playwright-browsers")
    if "--self-test" in sys.argv:
        if not (root / "config" / "settings.example.json").is_file():
            raise RuntimeError("Bundled configuration is missing")
        if not (installed_root / "chrome_extension" / "manifest.json").is_file():
            raise RuntimeError("Chrome extension files are missing")
        from docx import Document  # noqa: F401 - verify packaged dependency
        import gdown  # noqa: F401 - verify packaged Google Drive dependency
        from playwright.sync_api import sync_playwright
        if getattr(sys, "frozen", False):
            with sync_playwright() as playwright:
                if not Path(playwright.chromium.executable_path).is_file():
                    raise RuntimeError("Bundled Chromium executable is missing")
        print("Packaging self-test passed")
        return 0
    config_dir = Path.home() / ".ircenter-automation"
    config_dir.mkdir(parents=True, exist_ok=True)
    examples = root / "config"
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
