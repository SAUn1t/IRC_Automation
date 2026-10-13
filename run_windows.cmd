@echo off
setlocal
title IR Center app
cd /d "%~dp0"
if errorlevel 1 goto folder_failed

if not exist ".venv\Scripts\python.exe" goto setup_missing

echo Starting IR Center app...
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto app_failed

echo.
echo Application closed normally. Press any key to close this window.
pause
exit /b 0

:folder_failed
echo Could not open the extracted application folder.
goto failed

:setup_missing
echo Python environment is missing. Run setup_windows.cmd first.
goto failed

:app_failed
echo The application could not start or exited with an error. Read the message above.
goto failed

:failed
echo.
echo Press any key to close this window.
pause
exit /b 1
