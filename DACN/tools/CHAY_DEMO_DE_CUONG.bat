@echo off
cd /d "%~dp0.."
backend\venv\Scripts\python.exe tools\start_proposal.py
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8001/dashboard/"
exit /b 0
:failed
echo Khong khoi dong duoc. Xem thong bao ben tren va thu muc work.
pause
