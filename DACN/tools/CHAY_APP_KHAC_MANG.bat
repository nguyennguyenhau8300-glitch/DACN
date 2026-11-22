@echo off
cd /d "%~dp0.."
"backend\venv\Scripts\python.exe" "tools\demo_internet.py"
echo.
pause
