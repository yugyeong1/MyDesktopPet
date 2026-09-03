@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto NO_PYTHON
py -m pip install --upgrade pyinstaller Pillow
if errorlevel 1 goto ERROR
py -m PyInstaller --noconfirm --clean --onefile --windowed --name KongKongPet --add-data "assets;assets" desktop_pet.py
if errorlevel 1 goto ERROR
echo Build complete: %CD%\dist\MyBichonPet.exe
pause
exit /b 0
:NO_PYTHON
echo ERROR: Python was not found.
pause
exit /b 1
:ERROR
echo ERROR: Build failed.
pause
exit /b 1
