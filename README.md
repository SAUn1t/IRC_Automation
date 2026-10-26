# IR Center DOCX form assistant

Windows desktop application for processing **one child at a time**. Choose a local DOCX folder or a publicly shared Google Drive parent folder. Parsing and field validation run locally after the selected DOCX is available on the computer. Only the browser sends form data to `https://ircenter.gov.ua/` through the user's normal session. The app does not request or save a password, use an AI service, upload screenshots, or log personal field values.

## Current status

The app recognizes the supplied 11-section school IPR DOCX and the matching current 11-section portal form. The Chrome extension fills populated counterparts across the form, including adaptation notes, subject and goal tables, services, assessment choices, and team members. With `manual_review_only: true`, the browser stays open for review and any missing entries. The app does not press “Сформувати документ” or claim that the manual submission succeeded. See [template compatibility](docs/template_compatibility.md). This wider mapping has anonymized synthetic tests but has not been validated against a live authenticated session.

Section 9 (extension of study) is skipped during automatic filling, even when the DOCX has a marked Yes/No answer. Review that portal choice manually before generating the document.

The conclusions journal has a 10-column table: the name link is in column 2 and the IPR action is in column 8. The separate “Пошук висновку” page requires a birth date, certificate number, and CAPTCHA, so the app uses the authenticated journal instead. It scans every journal page (up to a 100-page safety limit), requires exactly one first-name and surname match, opens that row's IPR page, and confirms the name again. On the IPR page it accepts either the top “Створити ІПР” link or the plus icon in column 5 of the IPR table. It stops if both are shown, if multiple plus icons are shown, or if the create link belongs to another conclusion. The example config includes the observed navigation, form identity, and “Сформувати документ” selectors. Success and validation selectors remain placeholders for any future fully automated submission mode.

## Architecture

| Module | Responsibility |
| --- | --- |
| `normalization.py`, `documents.py`, `document_source.py` | Exact Unicode child matching; local or Google Drive DOCX discovery; local label/value extraction from paragraphs and tables |
| `settings.py`, `mapping.py` | Validated local settings and separate field mappings |
| `state.py`, `workflow.py` | Ordered state transitions and stop/continue/review gates |
| `browser.py`, `ircenter.py` | Browser launch or connection; site navigation, identity, form, and submission checks |
| `form_filler.py` | Fill and read back each field, then run a full verification pass |
| `gui/main_window.py` | PySide6 GUI and worker thread |

`requirements.txt` uses Python 3.12+, PySide6, Playwright, python-docx, gdown, and pytest. Google Drive mode downloads the chosen DOCX to a temporary local file for parsing; no separate processing service is used. Tagged releases build a Windows installer with Python, the Playwright browser, and the Chrome extension files. The user's settings and browser profile stay outside the installation folder.

## Windows installer and updates

Download and run [IRCenterAssistant-Setup.exe](https://github.com/SAUn1t/IRC_Automation/releases/latest/download/IRCenterAssistant-Setup.exe) once. It installs for the current Windows user and creates a Start menu shortcut. Python and `setup_windows.cmd` are not needed for the installer. The app automatically checks for a newer GitHub release when it opens. When one is available, click **Install update**; the app downloads the release installer, verifies its SHA-256 digest against GitHub's release metadata, installs it, and reopens. If a check cannot reach GitHub, the app still runs normally and **Check for updates** can retry it.

Existing settings, pairing code, document source choice, and browser profile remain in `%USERPROFILE%\.ircenter-automation`. To use the Chrome extension with the installer, load it once from `%LOCALAPPDATA%\Programs\IRCenterAssistant\chrome_extension` through `chrome://extensions` → **Load unpacked**, then pair it using the app's **Copy extension pairing code** button. If you previously loaded the extension from an extracted source ZIP, switch it to this stable installed path once. Future extension updates reload automatically when the app starts processing; if Chrome reports that the extension path is outdated, load it again from the installed folder.

The Windows release is built by `.github/workflows/release-windows.yml` when a version tag matching `ircenter_automation.__version__` is pushed. The installer is currently unsigned, so Windows may show a publisher warning on the first install.

## Choose the DOCX source

For documents on the computer, select **Local folder**, choose the DOCX folder, enter the child's first name and surname, and click **Process**. This preserves the existing local workflow.

For Google Drive, select **Google Drive**, paste a parent folder link from `https://drive.google.com/drive/folders/...`, and click **Save Drive link**. The parent folder and its contents must be shared with **Anyone with the link**. Enter the class folder name (for example, `7-A` or `6-Б`) and the child's first name and surname, then click **Process**. The app searches this structure:

```text
Shared parent folder/
  7-A/
    Пахомов Арсен В'ячеславович/
      ІПР 2026.docx
```

The child folder may include a patronymic; the two entered name words can be in either order. The DOCX filename can contain other text but must include `ІПР` (or `IPR`) and end in `.docx`. The app requires exactly one matching class folder, child folder, and IPR DOCX. It downloads only that file to a temporary folder, confirms the child's name inside the DOCX, then removes the temporary file after parsing. Native Google Docs and private Drive folders are not supported. Each folder must have fewer than 50 items so the public Drive listing can be checked completely.

## Source setup

Install Python 3.12 on Windows (other Python versions can remain installed). The Windows Python install manager supports `py install 3.12`; otherwise use the Python 3.12 installer from python.org. Extract the source bundle to a folder, then run `setup_windows.cmd` once and `run_windows.cmd` to open the app. Both scripts keep their command window open so you can read any error. Alternatively, in PowerShell from the repository directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --requirement requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py
```

On first launch, example configuration is copied to `%USERPROFILE%\.ircenter-automation\settings.json` and `field_mapping.json`. An older pair of untouched placeholder configs is upgraded automatically on launch while preserving the DOCX folder and browser choices. Customized configs are left alone; in that case, copy the new `selectors`, `website_url`, and `manual_review_only` entries from `config\settings.example.json` into your local settings, and update your mapping deliberately. These files and the persistent browser profile stay outside the checkout. Choose the document source in the GUI. The **Browser mode** selector offers **Chrome extension (existing profile)** (the new default), **Chrome normal window**, **Edge normal window**, and the prior Playwright launch modes. `browser_executable` can point to installed Chrome if it cannot be found automatically.

### Chrome extension setup

Chrome's Google sign-in may reject a browser started with remote debugging. The extension mode uses your existing Chrome profile and avoids remote debugging. The extension opens the conclusions journal in the Chrome profile where it is installed, then performs the matching, navigation, and current-form fill there. Install the extension once:

1. In your usual Chrome, open `chrome://extensions`, enable **Developer mode**, and click **Load unpacked**. For the installer, choose `%LOCALAPPDATA%\Programs\IRCenterAssistant\chrome_extension`; for a source checkout, choose its `chrome_extension` directory. Keep the extension enabled.
2. Start the desktop app and select **Chrome extension (existing profile)**. Click **Copy extension pairing code**. Open the extension's toolbar popup, paste the code, and click **Save pairing**. The code remains on your computer; never share it.
3. Keep that Chrome profile open. Enter the child's two-word name, select the DOCX source, and click **Process**. Within about 30 seconds after the document is parsed, the extension continues from an active conclusions journal, child IPR page, or “Створити ІПР” form. From other pages it opens the journal in a new tab. If an open IPR page or form belongs to another child, it leaves that tab alone and searches the journal in a new tab. It checks the child before filling matched fields, then stops for manual review. It does not press **Сформувати документ**.

Chrome requires the one-time manual extension installation. Installer updates automatically reload an extension loaded from the stable installed path when the app next processes a document. If Chrome still shows an older extension version, remove that installation and load the extension from the installed app folder. The app refuses jobs from outdated extensions; when an already open portal form has an old content script, it opens a fresh form tab and leaves any edits in the original tab untouched. Source checkout updates still require **Reload** on `chrome://extensions`. The portal may still require you to sign in through its normal page. The extension does not solve or override any security check. If the app says it is waiting for the extension, confirm the extension is enabled and paired in the same Chrome profile that can open the portal normally.

The journal accepts next-page links using either `?page=2` or `/page/2`. The extension opens each page as a normal Chrome navigation, so it can continue when the portal rejects background page requests. It starts from page 1 even if page 2 is already open, preserving the duplicate-name check across the whole journal. An unexpected portal link reports its route shape with numeric IDs hidden, so you can share that error without sharing a record ID.

If the portal shows Cloudflare “Performing security verification” in a Playwright launch mode, the app waits for the journal and does not reload the page when you press **Continue after login**. If the check loops while your ordinary Chrome works, select **Chrome extension (existing profile)**. **Chrome normal window** is a separate profile controlled through remote debugging; Google may reject sign-in there. The app does not override the portal's security check.

If the check works in your normal browser but keeps looping in the app browser, press **Stop** in the app. Enter the child's two-word name and click **Copy fields for normal browser**. This reads the DOCX locally, confirms the child's name, and offers copy buttons for the four exact fields. Open the matching child's **Створити ІПР** form in your normal browser, paste each value into its labeled field, and review all remaining sections before using **Сформувати документ**. The copy guide does not connect to the portal or submit anything.

## Connecting to IR Center

1. For the default Chrome extension workflow, use the current 11-section mapping. The `field_mapping.json` file applies to the separate Playwright modes. Redact names and personal values before sharing any DOM excerpts. Do not share passwords, cookies, browser profiles, or full page dumps containing personal data.
2. The journal name and IPR links are scoped to each row. Pagination must expose a usable “Далі” link on every nonfinal page; unexpected or looping links stop processing. The IPR page and form names are parsed only in the observed surname, first name, patronymic order. The DOCX child name must also match the requested child before the browser opens.
3. Map actual DOCX labels to form controls in `field_mapping.json`. Supported `control` values: `text`, `textarea`, `date`, `select`, `radio`, `checkbox`, `autocomplete`, `richtext`. `select` uses `options` from document value to HTML option value; `radio` maps document value to a CSS selector; `autocomplete` needs `option_selector`. `verification_selector` and `verification_mode: "text"` can read a displayed selected value when the input itself is not authoritative.
4. Keep `manual_review_only: true` while using this DOCX layout. The Chrome extension fills and verifies matched populated fields, keeps the browser open, and leaves completion and “Сформувати документ” to you. Check whether opening “Створити ІПР” itself creates a draft.
5. A future complete mapping may use `manual_review_only: false` only after all fields, validation states, and a confirmed success signal are implemented and tested. Keep `dry_run: true` and `review_before_submit: true` until then.

The application does not guess selectors or choose among duplicate exact-name records. It cannot establish a unique identity if the database has multiple records with the same first name and surname; the workflow stops and requires additional deterministic identification. It never retries final submission automatically. A success indicator must be configured from an actual confirmed save response; a click alone is insufficient.

## DOCX assumptions and limitations

The generic parser recognizes `Label: value` paragraphs and table rows with adjacent label/value cells. It retains empty values and line breaks within values. It recognizes visible Unicode checkbox glyphs `☑`, `☒`, `☐`; complex Word content controls require a template-specific parser. Duplicate labels and ambiguous table rows stop processing. The mapping must cover each required website field. The sample mapping is illustrative, not a claim about the real document or website.

Local filename patterns are deterministic and exact apart from Unicode normalization, whitespace folding, and case folding. Enter exactly two words for the child. For the supported school IPR DOCX, either first name then surname or surname then first name is accepted; the app confirms their order against the document's labeled full name before opening the portal. A patronymic is not required in the input. Local mode searches only `.docx` files directly in the selected folder. Google Drive mode uses the class and child folders described above.

## Safety notes

- The persistent browser profile is in `~/.ircenter-automation/browser-profile`; protect it as an authenticated session. Do not commit or share it.
- Chrome extension mode opens an authenticated local bridge on `127.0.0.1:38417` only while processing. The extension stores its pairing token in Chrome's extension storage. Remove the extension and its pairing data if you stop using this mode.
- Normal window mode opens a local debugging port for the dedicated Chrome or Edge profile while the app runs. Close the app when finished; do not use this profile for unrelated browsing.
- Status messages shown in the GUI include the child's name and DOCX filename for the user's review. Technical logs only record state names and contain no field values.
- An ambiguous submit response is reported as **SUBMISSION NOT CONFIRMED**; inspect the website before trying again.
- Stop requests are honored between browser actions and while waiting for manual login/review. An in-progress Playwright action may take up to the configured timeout to stop.
