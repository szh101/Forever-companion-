@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Installation complete. Run start-windows.cmd when you want to open the companion.
pause
exit /b 0
:fail
echo Setup failed. Install Python 3.11 or newer from python.org with Tcl/Tk and the Python launcher.
pause
exit /b 1
