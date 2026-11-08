@echo off
cd /d "%~dp0"
title Claugineer - simulated demo
if not exist pycmd.txt (echo Run install.bat first. & pause & exit /b 1)
set /p PY=<pycmd.txt
echo Generating 14 simulated laps, then opening the dashboard...
%PY% -m claugineer sim --laps 14
pause
