@echo off
rem Run the Workbay server on its own FROM SOURCE (for the PC that hosts
rem a shared LAN database). Other PCs point their client at this PC's
rem address.
rem
rem If you have the built exe you do not need this file or Python at
rem all: run "Workbay.exe --server" instead.
setlocal
cd /d "%~dp0"

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3 server.py
    goto :eof
)

python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    python server.py
    goto :eof
)

echo.
echo Python 3 is not installed (the Microsoft Store stub does not count).
echo Install it from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run this again.
echo.
pause
