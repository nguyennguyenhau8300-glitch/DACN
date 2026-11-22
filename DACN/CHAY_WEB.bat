@echo off
cd /d "%~dp0backend"
python main.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Khong khoi dong duoc. Xem thong bao ben tren.
pause
