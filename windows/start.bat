@echo off
cd /d "%~dp0"

echo Checking dependencies...
pip install -q -r requirements.txt 2>nul

echo Starting Claude Usage Widget...
start "" pythonw widget.pyw
echo Widget started. Look for the floating overlay.
