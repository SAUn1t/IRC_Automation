@echo off
setlocal
title IR Center setup
cd /d "%~dp0"
if errorlevel 1 goto folder_failed

echo Setting up IR Center in "%CD%"
echo.

py -3.12 --version >nul 2>&1
if errorlevel 1 goto missing_python

echo Creating Python environment...
py -3.12 -m venv .venv
if errorlevel 1 goto venv_failed

echo Installing Python packages...
".venv\Scripts\python.exe" -m pip install --requirement requirements.txt
if errorlevel 1 goto packages_failed

echo Installing Chromium for Playwright...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto browser_failed

echo.
echo Setup complete. Run run_windows.cmd to open the application.
pause
exit /b 0

:folder_failed
echo Could not open the extracted application folder.
goto failed

:missing_python
echo Python 3.12 was not found. Install Python 3.12 from python.org, then run this file again.
goto failed

:venv_failed
echo Could not create the Python environment.
goto failed

:packages_failed
echo Python package installation failed.
goto failed

:browser_failed
echo Chromium installation failed. Check the download error above.
goto failed

:failed
echo.
echo Setup stopped. The error is shown above. Press any key to close this window.
pause
exit /b 1
