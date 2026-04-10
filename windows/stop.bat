@echo off
echo Stopping Claude Usage Widget...
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq Claude Usage" 2>nul
taskkill /f /fi "MODULES eq claude-usage.py" 2>nul
echo Done.
