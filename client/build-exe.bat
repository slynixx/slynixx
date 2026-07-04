@echo off
rem Build the final standalone Workbay.exe (single file, no console).
rem
rem Required flags -- do not remove any of these:
rem   --onefile --windowed        single silent exe
rem   --add-data "assets;assets"  bundle the icon/assets
rem   --add-data "..\server;server"  bundle the server so the exe can run
rem                                  it in-process on a daemon thread
rem   --paths "..\server"         let PyInstaller analyse server imports
rem   hidden imports server_manager secrets sqlite3 hashlib db auth
rem       (the bundled server fails with ModuleNotFoundError without them)
setlocal
cd /d "%~dp0"

set PYCMD=
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set PYCMD=py -3
if not defined PYCMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set PYCMD=python
)
if not defined PYCMD (
    echo.
    echo Python 3 is not installed ^(the Microsoft Store stub does not count^).
    echo Install it from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

%PYCMD% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    %PYCMD% -m pip install pyinstaller
    if errorlevel 1 (
        echo Could not install PyInstaller. Check your internet connection.
        pause
        exit /b 1
    )
)

if not exist "assets\workbay.ico" %PYCMD% assets\generate_icon.py

echo Building Workbay.exe ...
%PYCMD% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Workbay ^
    --icon "assets\workbay.ico" ^
    --add-data "assets;assets" ^
    --add-data "..\server;server" ^
    --paths "..\server" ^
    --hidden-import server_manager ^
    --hidden-import secrets ^
    --hidden-import sqlite3 ^
    --hidden-import hashlib ^
    --hidden-import db ^
    --hidden-import auth ^
    app.py
if errorlevel 1 (
    echo.
    echo Build FAILED. See the messages above.
    pause
    exit /b 1
)

echo.
echo Build finished: %~dp0dist\Workbay.exe
pause
