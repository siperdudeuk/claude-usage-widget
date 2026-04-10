@echo off
cd /d "%~dp0"

echo ===================================
echo  Claude Usage Widget — Install
echo ===================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo Done.
echo.

:: Create Start Menu shortcut
echo Creating Start Menu shortcut...
set SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs
set VBS_TEMP=%TEMP%\create_shortcut.vbs

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_TEMP%"
echo Set oLink = oWS.CreateShortcut("%SHORTCUT_DIR%\Claude Usage Widget.lnk") >> "%VBS_TEMP%"
echo oLink.TargetPath = "pythonw" >> "%VBS_TEMP%"
echo oLink.Arguments = """%~dp0widget.pyw""" >> "%VBS_TEMP%"
echo oLink.WorkingDirectory = "%~dp0" >> "%VBS_TEMP%"
echo oLink.Description = "Claude AI Usage Monitor" >> "%VBS_TEMP%"
echo oLink.Save >> "%VBS_TEMP%"
cscript //nologo "%VBS_TEMP%"
del "%VBS_TEMP%"

echo.
echo ===================================
echo  Installed successfully!
echo.
echo  You can now:
echo    1. Search "Claude Usage Widget" in Start Menu
echo    2. Or run start.bat
echo.
echo  Make sure you're logged into claude.ai in Chrome.
echo ===================================
pause
