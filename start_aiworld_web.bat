@echo off
rem Start the whole simulated Internet (Omnipedia, the Herald, the Almanac
rem and Farsight Search) at once.  Open http://omnipedia.localhost/ to begin.
cd /d "%~dp0"
echo Starting the AIWORLD simulated Internet...
echo   Omnipedia              http://omnipedia.localhost/
echo   The Zyphoran Herald    http://zyphoranherald.localhost/
echo   Navigator's Almanac    http://navigatorsalmanac.localhost/
echo   Farsight Search        http://farsight.localhost/
echo   (fallback ports: 5000-5003)
echo Press CTRL+C to stop everything.
python aiworld_web.py
pause