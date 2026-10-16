@echo off
rem AIWORLD - one-time setup: install Python dependencies and check Ollama.
rem Runs as your normal user (no administrator rights needed).
setlocal
cd /d "%~dp0"

echo ============================================================
echo AIWORLD setup
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3 from https://www.python.org/downloads/
    echo         and make sure "Add Python to PATH" is ticked.
    pause
    exit /b 1
)

echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Could not install the dependencies. See the messages above.
    pause
    exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo [WARN] Ollama was not found on PATH.
    echo        Install it from https://ollama.com/download
    echo        then run:  ollama pull qwen3:14b
) else (
    echo.
    echo Ollama found. If you have no model installed yet, run:
    echo     ollama pull qwen3:14b
)

echo.
echo Setup done. Start AIWORLD with start_aiworld.bat
pause
