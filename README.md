# IR Center local DOCX form assistant

Windows desktop application for processing **one child at a time**. DOCX discovery, parsing, and field validation run locally. Only the browser sends form data to `https://ircenter.gov.ua/` through the user's normal session. The app does not request or save a password, use an AI service, upload screenshots, or log personal field values.

## Current status

The base application is implemented. **Preview DOCX locally** works without the website and shows the selected file and number of parsed labels. The remaining website selectors and actual DOCX-to-form mapping are intentionally unconfigured because the full workflow DOM and template have not been provided. **Process stops before browser navigation while these placeholders remain.** Do not enable submission until a real form has been mapped and tested. The app defaults to `dry_run: true` and `review_before_submit: true`.

The supplied conclusions-list HTML confirms a 10-column table: the name link is in column 2 and the IPR action is in column 8. The example config now contains selectors for that row structure. Its name parser accepts only the observed `Surname First Patronymic` format, and the action link is resolved within the exact matched row. The list also has pagination; the app still stops when more pages may contain matches. The eighth-cell link points to an IPR route, but its destination behavior has not yet been verified. Search, record, form, and submission selectors remain placeholders.

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

On first launch, example configuration is copied to `%USERPROFILE%\.ircenter-automation\settings.json` and `field_mapping.json`. These files and the persistent browser profile stay outside the checkout. Choose the DOCX folder in the GUI. Chrome or Edge can be selected by setting `browser` to `chrome` or `msedge`; the default Chromium binary is installed by Playwright. `browser_executable` can point to a locally installed Chromium binary when the Playwright download is unavailable. The default `browser_headless: false` keeps manual login possible.

## Connecting to IR Center

1. Inspect the site's search, result, record, new-form, form-field, validation-error, and success elements **while logged in manually**. Redact names and personal values before sharing DOM excerpts. Do not share passwords, cookies, browser profiles, or full page dumps containing personal data.
2. Replace every `REPLACE_AFTER_DOM_INSPECTION` in the local settings with a stable CSS selector, except `form_heading_text`, which is the expected visible title. Result first/surname selectors are relative to each result row; all others are page selectors. `next_results_page` must identify any usable next-page control so a partial result list stops processing. Infinite-scroll result lists need an additional site-specific completeness check. The record and form must expose first and surname separately. If they do not, the adapter needs a site-specific safe parser before use.
3. Map actual DOCX labels to form controls in `field_mapping.json`. Supported `control` values: `text`, `textarea`, `date`, `select`, `radio`, `checkbox`, `autocomplete`, `richtext`. `select` uses `options` from document value to HTML option value; `radio` maps document value to a CSS selector; `autocomplete` needs `option_selector`. `verification_selector` and `verification_mode: "text"` can read a displayed selected value when the input itself is not authoritative.
4. Keep `dry_run: true` while testing with a **synthetic or authorized test record**. A dry run can navigate and fill but never presses final Submit. Check the website state manually afterward, including whether opening a form itself creates a draft.
5. Once the site behavior is confirmed, set `dry_run: false` while keeping `review_before_submit: true`. The UI then waits for a separate Submit click after complete verification. `auto_submit: true` is supported only with `review_before_submit: false` and should be reserved for a separately validated workflow.

The application does not guess selectors or choose among duplicate exact-name records. It cannot establish a unique identity if the database has multiple records with the same first name and surname; the workflow stops and requires additional deterministic identification. It never retries final submission automatically. A success indicator must be configured from an actual confirmed save response; a click alone is insufficient.

## DOCX assumptions and limitations

The generic parser recognizes `Label: value` paragraphs and table rows with adjacent label/value cells. It retains empty values and line breaks within values. It recognizes visible Unicode checkbox glyphs `☑`, `☒`, `☐`; complex Word content controls require a template-specific parser. Duplicate labels and ambiguous table rows stop processing. The mapping must cover each required website field. The sample mapping is illustrative, not a claim about the real document or website.

Filename patterns are deterministic and exact apart from Unicode normalization, whitespace folding, and case folding. Input currently requires two words, first name then surname; this avoids guessing which part of a multiword name is which. Only `.docx` files directly in the selected folder are searched.

## Safety notes

- The persistent browser profile is in `~/.ircenter-automation/browser-profile`; protect it as an authenticated session. Do not commit or share it.
- Status messages shown in the GUI include the child's name and DOCX filename for the user's review. Technical logs only record state names and contain no field values.
- An ambiguous submit response is reported as **SUBMISSION NOT CONFIRMED**; inspect the website before trying again.
- Stop requests are honored between browser actions and while waiting for manual login/review. An in-progress Playwright action may take up to the configured timeout to stop.
