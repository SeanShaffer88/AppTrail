@echo off
cd /d "%~dp0"
python -m apptrail gui
if errorlevel 1 pause
