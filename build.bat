@echo off
chcp 65001 >nul
echo ========================================
echo   Afterburner - Build EXE
echo ========================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller
echo.
echo Building executable...
pyinstaller --onefile ^
    --windowed ^
    --name "Afterburner" ^
    --icon NONE ^
    --add-data "requirements.txt;." ^
    monitor.py
echo.
echo Build complete! Check the 'dist' folder.
pause
