@echo off
REM Opens a NEW Command Prompt window in this repo with .venv already activated.
REM Good for double-click from Explorer. For an existing window, use activate_venv.bat instead.

set "REPO=%~dp0"
cd /d "%REPO%"

if not exist "%REPO%.venv\Scripts\activate.bat" (
    echo [.venv not found at "%REPO%.venv"]
    echo Create it:  python -m venv .venv
    echo Then install:  pip install -e ".[dev]"
    pause
    exit /b 1
)

start "Sabi MouthingSpeech (venv)" cmd /k cd /d "%REPO%" ^&^& call "%REPO%.venv\Scripts\activate.bat"
