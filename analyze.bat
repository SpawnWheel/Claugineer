@echo off
cd /d "%~dp0"
if not exist pycmd.txt (echo Run install.bat first. & pause & exit /b 1)
set /p PY=<pycmd.txt
%PY% -m claugineer analyze latest
pause
