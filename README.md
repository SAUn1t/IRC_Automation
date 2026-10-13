# IR Center local DOCX form assistant

Windows desktop application for processing **one child at a time**. DOCX discovery, parsing, and field validation run locally. Only the browser sends form data to `https://ircenter.gov.ua/` through the user's normal session. The app does not request or save a password, use an AI service, upload screenshots, or log personal field values.

## Current status

The app now recognizes the supplied 11-section school IPR DOCX layout and can transfer four scalar fields with direct counterparts in the portal form: execution period, year of study, class, and parent contact numbers. The sample settings enable `manual_review_only: true`: after those four fields are filled and read back, the browser stays open for the user to complete and review the rest. Press **Stop** to close the browser. The app does not press “Сформувати документ” or claim that the manual submission succeeded. See [template compatibility](docs/template_compatibility.md). This workflow has synthetic browser tests but has not been validated against a live authenticated session.

The conclusions journal has a 10-column table: the name link is in column 2 and the IPR action is in column 8. The separate “Пошук висновку” page requires a birth date, certificate number, and CAPTCHA, so the app uses the authenticated journal instead. It scans every journal page (up to a 100-page safety limit), requires exactly one first-name and surname match, opens that row's IPR page, and confirms the name again. On the IPR page it accepts either the top “Створити ІПР” link or the plus icon in column 5 of the IPR table. It stops if both are shown, if multiple plus icons are shown, or if the create link belongs to another conclusion. The example config includes the observed navigation, form identity, and “Сформувати документ” selectors. Success and validation selectors remain placeholders for any future fully automated submission mode.

## Architecture

| Module | Responsibility |
| --- | --- |
| `normalization.py`, `documents.py` | Exact Unicode child and filename matching; local DOCX label/value extraction from paragraphs and tables |
| `settings.py`, `mapping.py` | Validated local settings and separate field mappings |
| `state.py`, `workflow.py` | Ordered state transitions and stop/continue/review gates |
| `browser.py`, `ircenter.py` | Persistent Playwright browser; site navigation, identity, form, and submission checks |
| `form_filler.py` | Fill and read back each field, then run a full verification pass |
| `gui/main_window.py` | PySide6 GUI and worker thread |

`requirements.txt` uses Python 3.12+, PySide6, Playwright, python-docx, and pytest. No remote processing service is used. A future PyInstaller build can bundle the Python app; Playwright browser binaries and the user's profile still need an explicit packaging plan.

## Windows setup

Install Python 3.12 on Windows (other Python versions can remain installed). The Windows Python install manager supports `py install 3.12`; otherwise use the Python 3.12 installer from python.org. Extract the source bundle to a folder, then run `setup_windows.cmd` once and `run_windows.cmd` to open the app. Both scripts keep their command window open so you can read any error. Alternatively, in PowerShell from the repository directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --requirement requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py
```

On first launch, example configuration is copied to `%USERPROFILE%\.ircenter-automation\settings.json` and `field_mapping.json`. An older pair of untouched placeholder configs is upgraded automatically on launch while preserving the DOCX folder and browser choices. Customized configs are left alone; in that case, copy the new `selectors`, `website_url`, and `manual_review_only` entries from `config\settings.example.json` into your local settings, and update your mapping deliberately. These files and the persistent browser profile stay outside the checkout. Choose the DOCX folder in the GUI. Chrome or Edge can be selected by setting `browser` to `chrome` or `msedge`; the default Chromium binary is installed by Playwright. `browser_executable` can point to a locally installed Chromium binary when the Playwright download is unavailable. The default `browser_headless: false` keeps manual login possible.

## Connecting to IR Center

1. For the default manual review workflow, use the supplied site selectors and four-field mapping after updating the local config as described above. Redact names and personal values before sharing any DOM excerpts. Do not share passwords, cookies, browser profiles, or full page dumps containing personal data.
2. The journal name and IPR links are scoped to each row. Pagination must expose a usable “Далі” link on every nonfinal page; unexpected or looping links stop processing. The IPR page and form names are parsed only in the observed surname, first name, patronymic order. The DOCX child name must also match the requested child before the browser opens.
3. Map actual DOCX labels to form controls in `field_mapping.json`. Supported `control` values: `text`, `textarea`, `date`, `select`, `radio`, `checkbox`, `autocomplete`, `richtext`. `select` uses `options` from document value to HTML option value; `radio` maps document value to a CSS selector; `autocomplete` needs `option_selector`. `verification_selector` and `verification_mode: "text"` can read a displayed selected value when the input itself is not authoritative.
4. Keep `manual_review_only: true` while using this DOCX layout. The app fills and verifies only the four listed fields, keeps the browser open, and leaves completion and “Сформувати документ” to you. Check whether opening “Створити ІПР” itself creates a draft.
5. A future complete mapping may use `manual_review_only: false` only after all fields, validation states, and a confirmed success signal are implemented and tested. Keep `dry_run: true` and `review_before_submit: true` until then.

The application does not guess selectors or choose among duplicate exact-name records. It cannot establish a unique identity if the database has multiple records with the same first name and surname; the workflow stops and requires additional deterministic identification. It never retries final submission automatically. A success indicator must be configured from an actual confirmed save response; a click alone is insufficient.

## DOCX assumptions and limitations

The generic parser recognizes `Label: value` paragraphs and table rows with adjacent label/value cells. It retains empty values and line breaks within values. It recognizes visible Unicode checkbox glyphs `☑`, `☒`, `☐`; complex Word content controls require a template-specific parser. Duplicate labels and ambiguous table rows stop processing. The mapping must cover each required website field. The sample mapping is illustrative, not a claim about the real document or website.

Filename patterns are deterministic and exact apart from Unicode normalization, whitespace folding, and case folding. Input currently requires two words, first name then surname; this avoids guessing which part of a multiword name is which. Only `.docx` files directly in the selected folder are searched.

## Safety notes

- The persistent browser profile is in `~/.ircenter-automation/browser-profile`; protect it as an authenticated session. Do not commit or share it.
- Status messages shown in the GUI include the child's name and DOCX filename for the user's review. Technical logs only record state names and contain no field values.
- An ambiguous submit response is reported as **SUBMISSION NOT CONFIRMED**; inspect the website before trying again.
- Stop requests are honored between browser actions and while waiting for manual login/review. An in-progress Playwright action may take up to the configured timeout to stop.
