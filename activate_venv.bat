@echo off
REM Activate the project's .venv in THIS Command Prompt window.
REM Usage:  cd to repo (or run with full path), then:  activate_venv.bat

set "REPO=%~dp0"
cd /d "%REPO%"

if not exist "%REPO%.venv\Scripts\activate.bat" (
    echo [.venv not found at "%REPO%.venv"]
    echo Create it:  python -m venv .venv
    echo Then install:  pip install -e ".[dev]"
    exit /b 1
)

call "%REPO%.venv\Scripts\activate.bat"
echo.
echo Virtual environment activated ^(you should see (.venv) in your prompt^).
