@echo off
REM Build a standalone SidePeek.exe with PyInstaller.
REM Requires: python on PATH, pip install pyinstaller (installed automatically below).

setlocal
cd /d "%~dp0"

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [build] installing pyinstaller...
    python -m pip install --upgrade pyinstaller || goto :err
)

echo [build] building...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name SidePeek ^
    run.py || goto :err

echo.
echo [build] done -^> dist\SidePeek.exe
echo [build] config.json will be created next to the exe on first run.
goto :eof

:err
echo.
echo [build] FAILED
exit /b 1
