@echo off
rem One-time setup for this package: creates a Python virtual environment,
rem installs dependencies, and scaffolds a .env file for your own
rem Cyclomedia credentials. Run this once before any of the start_*.bat
rem launchers. Needs Python 3.10+ -- either already on PATH, or you can
rem point this script at an existing install elsewhere on this computer
rem (e.g. Anaconda/Miniconda, which doesn't add itself to PATH by default).
setlocal enabledelayedexpansion
cd /d "%~dp0"

set PYTHON_CMD=python
call :CHECK_PYTHON
if "%PYTHON_OK%"=="1" goto INSTALL

echo.
echo ============================================================
echo  Python 3.10 or newer was not found (or the installed version
echo  is too old) on this computer's PATH.
echo ============================================================
echo.
echo  If you have Anaconda or Miniconda installed, here's how to find
echo  its python.exe:
echo    1. Open "Anaconda Prompt" from the Start menu.
echo    2. Run:  where python
echo    3. Copy the first path it prints (e.g.
echo       C:\Users\YourName\anaconda3\python.exe).
echo  A path copied from Windows Explorer ("Copy as path") also works.
echo.
set /p CUSTOM_PYTHON="Already have Python 3.10+ installed somewhere else? Enter the full path to python.exe below, or press Enter to open the download page instead: "
set CUSTOM_PYTHON=%CUSTOM_PYTHON:"=%
if "%CUSTOM_PYTHON%"=="" goto NO_PYTHON

set PYTHON_CMD="%CUSTOM_PYTHON%"
call :CHECK_PYTHON
if "%PYTHON_OK%"=="1" goto INSTALL

echo.
echo  That path didn't work -- not found, or not Python 3.10+.
echo.

:NO_PYTHON
echo.
echo ============================================================
echo  A Python download page will now open in your browser.
echo ============================================================
echo.
echo    1. Download the latest "Windows installer (64-bit)" for
echo       Python 3 from python.org.
echo    2. Run the installer.
echo    3. IMPORTANT: on the first install screen, check the box
echo       that says "Add python.exe to PATH" before clicking
echo       "Install Now".
echo    4. When the installer finishes, close this window and
echo       double-click setup.bat again.
echo.
start https://www.python.org/downloads/
pause
exit /b 1

:INSTALL
%PYTHON_CMD% -m venv venv
venv\Scripts\pip install -r requirements.txt
if not exist .env (
    copy .env.example .env
    echo Created .env from .env.example -- edit it with your own Cyclomedia credentials before fetching new panoramas.
)
echo.
echo Setup complete. See README.md for what to run next.
echo To install the Chrome capture extension, see extension\INSTALL_GUIDE.html
echo (open it in a browser) for a full step-by-step walkthrough with screenshots.
pause
goto :EOF

:CHECK_PYTHON
set PYTHON_OK=0
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 goto :EOF
for /f "tokens=2 delims= " %%v in ('%PYTHON_CMD% --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if !PY_MAJOR! GTR 3 set PYTHON_OK=1
if !PY_MAJOR! EQU 3 if !PY_MINOR! GEQ 10 set PYTHON_OK=1
goto :EOF
