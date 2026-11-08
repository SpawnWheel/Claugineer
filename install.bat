@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Claugineer - install
echo.
echo  ==== Claugineer installer ====
echo.
set "PY="
where py >nul 2>nul && py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
)
if not defined PY (
  echo Python 3.9+ was not found. Installing Python 3.12 for your user with winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  ) else (
    echo.
    echo Could not install Python automatically.
    echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
    echo and run install.bat again.
    pause
    exit /b 1
  )
)
echo Using Python: !PY!
> pycmd.txt echo !PY!
!PY! -c "import sys;print(' Python', sys.version.split()[0], 'OK')"
echo.
echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Claugineer.lnk');$s.TargetPath='%~dp0run.bat';$s.WorkingDirectory='%~dp0';$s.IconLocation='%SystemRoot%\System32\shell32.dll,43';$s.Save()"
echo.
echo Checking AMS2 connection (fine if the game is closed right now)...
!PY! -m claugineer doctor
echo.
echo  Done. Next steps:
echo   1. In AMS2: Options ^> System ^> Shared Memory = Project CARS 2
echo   2. Double-click "Claugineer" on the desktop (or run.bat) before you drive.
echo   3. Want to see it working first? Run sim.bat for a simulated demo session.
echo.
pause
