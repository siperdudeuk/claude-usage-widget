@echo off
setlocal
cd /d "%~dp0"
cd ..

echo Pulling latest changes...
git pull --ff-only
if %errorlevel% neq 0 (
    echo ERROR: git pull failed
    exit /b 1
)

cd windows

echo Installing dependencies...
pip install -q -r requirements.txt

echo Restarting widget...
taskkill /f /im pythonw.exe 2>nul
timeout /t 2 /nobreak >nul
start "" pythonw widget.pyw

echo Update complete.
