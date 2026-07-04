@echo off
rem Run the Workbay client from source (auto-starts a hidden local server).
rem Windows ships fake python.exe Store stubs that pass "where python" but
rem do nothing, so we test Python by actually executing it.
setlocal
cd /d "%~dp0"

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    start "" /b pyw -3 app.py
    goto :eof
)

python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    start "" /b pythonw app.py
    goto :eof
)

echo.
echo Python 3 is not installed (the Microsoft Store stub does not count).
echo Install it from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run this again.
echo.
pause
