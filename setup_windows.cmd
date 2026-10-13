@echo off
setlocal
title IR Center setup
cd /d "%~dp0"
if errorlevel 1 goto folder_failed

echo Setting up IR Center in "%CD%"
echo.

echo Creating Python environment...
py -3.12 -m venv .venv
if errorlevel 1 goto venv_failed
if not exist ".venv\Scripts\python.exe" goto missing_python
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))"
if errorlevel 1 goto missing_python

echo Installing Python packages...
".venv\Scripts\python.exe" -m pip install --requirement requirements.txt
if errorlevel 1 goto packages_failed

echo Installing Chromium for Playwright...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 echo Chromium download failed. Local DOCX preview still works; configure Edge or retry the browser download before website automation.

echo.
echo Setup complete. Run run_windows.cmd to open the application.
pause
exit /b 0

:folder_failed
echo Could not open the extracted application folder.
goto failed

:missing_python
echo Python 3.12 was not found in the environment.
echo Run "py install 3.12" in Command Prompt, or install Python 3.12 from python.org.
echo Other Python versions can remain installed. Then run this setup file again.
goto failed

:venv_failed
echo Could not create the Python environment.
goto failed

:packages_failed
echo Python package installation failed.
goto failed

:failed
echo.
echo Setup stopped. The error is shown above. Press any key to close this window.
pause
exit /b 1
