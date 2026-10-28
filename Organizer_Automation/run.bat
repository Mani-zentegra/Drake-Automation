@echo off
title Drake Tax Organizer Automation Runner
cd /d "%~dp0"

echo =================================================================
echo        DRAKE TAX 2025: DYNAMIC TAX ORGANIZER AUTOMATION
echo =================================================================
echo.
echo Make sure Drake 2025 Tax Software is open on your screen!
echo.

python organizer_automation.py

echo.
echo =================================================================
echo Execution finished.
pause
