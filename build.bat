@echo off
setlocal

echo === [1/3] Installing/upgrading PyInstaller ===
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller. Make sure Python is in PATH.
    pause
    exit /b 1
)

echo.
echo === [2/3] Installing runtime dependencies ===
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)

echo.
echo === [3/3] Building executable ===
pyinstaller ^
    --noconfirm ^
    --noconsole ^
    --onedir ^
    --name ScreenshotToTerminal ^
    screenshot_to_terminal.pyw
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Done!
echo Executable: dist\ScreenshotToTerminal\ScreenshotToTerminal.exe
echo The whole dist\ScreenshotToTerminal\ folder is the redistributable.
echo ============================================
echo.
pause
