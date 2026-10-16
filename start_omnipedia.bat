@echo off
rem Start the local Omnipedia website.
cd /d "%~dp0"
echo Starting Omnipedia at http://127.0.0.1:5000/ ...
python omnipedia.py
pause
