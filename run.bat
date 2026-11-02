@echo off
cd /d "%~dp0Tax_Extraction_Tool"
echo Starting Drake Tax Automation server...
start http://127.0.0.1:5050
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" app.py
pause
