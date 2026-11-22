@echo off
chcp 65001 >nul
title Parkly - Backend cho ung dung Android
cd /d "%~dp0.."
echo Parkly - May chu cho ung dung Android
echo Dien thoai va may tinh can cung Wi-Fi.
echo Giu cua so nay mo trong khi su dung ung dung.
echo.
powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://127.0.0.1:8002/health/ready' -TimeoutSec 3; if ($r.status -eq 'ready') { exit 0 }; exit 1 } catch { exit 1 }"
if not errorlevel 1 (
    echo Backend cong 8002 da dang chay. Ban co the dang nhap tren dien thoai.
    pause
    exit /b 0
)
"backend\venv\Scripts\python.exe" tools\run_dashboard.py --lan --port 8002
echo.
echo Backend da dung.
pause
