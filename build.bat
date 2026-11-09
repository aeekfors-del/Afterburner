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
    --hidden-import config ^
    --hidden-import collector ^
    --hidden-import ui_widgets ^
    --hidden-import plyer ^
    --add-data "requirements.txt;." ^
    main.py
echo.
echo Build complete! Check the 'dist' folder.
pause
