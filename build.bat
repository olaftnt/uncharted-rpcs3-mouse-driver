@echo off
rem Builds dist\UnchartedMouseAim.exe (requires: pip install pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --console --icon assets\icon.ico --name UnchartedMouseAim uncharted_mouse_aim.py || exit /b 1
echo.
echo Built: %~dp0dist\UnchartedMouseAim.exe
