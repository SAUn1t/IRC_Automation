@echo off
setlocal
cd /d "%~dp0"

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 is required. Install it from python.org, then run this file again.
    exit /b 1
)

py -3.12 -m venv .venv
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -m pip install --requirement requirements.txt
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed

echo Setup complete. Run run_windows.cmd to open the application.
exit /b 0

:failed
echo Setup failed. Read the error above and retry after fixing it.
exit /b 1
