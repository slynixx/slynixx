@echo off
rem Run the Workbay server on its own (for the PC that hosts a shared
rem LAN database). Other PCs point their client at this PC's address.
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
