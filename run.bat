@echo off
chcp 65001 >nul
echo ========================================
echo   Afterburner - System Monitor
echo ========================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting Afterburner...
echo.
python monitor.py
pause
