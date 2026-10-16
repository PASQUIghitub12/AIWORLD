@echo off
rem AIWORLD - start the launcher menu.
rem Uses the built AIWORLD.exe if present, otherwise the Python launcher.
cd /d "%~dp0"

if exist "AIWORLD.exe" (
    "AIWORLD.exe" %*
) else (
    python aiworld_launcher.py %*
)
