@echo off
rem Builds dist\UC3MouseAim.exe (requires: pip install pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --console --icon assets\icon.ico --name UC3MouseAim uc3_mouse_aim.py || exit /b 1
echo.
echo Built: %~dp0dist\UC3MouseAim.exe
