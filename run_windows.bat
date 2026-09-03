@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto NO_PYTHON
py -c "import PIL" >nul 2>nul
if errorlevel 1 py -m pip install Pillow
if errorlevel 1 goto ERROR
py "desktop_pet.py"
if errorlevel 1 goto ERROR
exit /b 0
:NO_PYTHON
echo ERROR: Python was not found.
pause
exit /b 1
:ERROR
echo ERROR: Desktop Pet failed.
pause
exit /b 1
