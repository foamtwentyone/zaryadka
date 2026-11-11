@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name Zaryadka run.py
echo.
echo Готово: dist\Zaryadka.exe
pause
