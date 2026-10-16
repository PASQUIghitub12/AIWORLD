@echo off
rem Start the World Resident (in-world AI that browses the simulated Internet).
rem It will start the whole simulated Internet automatically if needed.
cd /d "%~dp0"
echo Starting AIWORLD World Resident...
python world_resident.py
pause
