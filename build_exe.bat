@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name Zaryadka --hidden-import hid run.py
echo.
echo Готово: dist\Zaryadka.exe
pause
