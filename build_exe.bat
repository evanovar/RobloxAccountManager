@echo off
echo ========================================
echo Building Roblox Account Manager EXE
echo ========================================
echo.

REM Check if PyInstaller is installed
py -m pip show PyInstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    py -m pip install PyInstaller
    echo.
)

REM Build the executable
echo Building executable with PyInstaller...
echo.
python -m PyInstaller --clean RobloxAccountManager.spec

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Build failed!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo The executable is located at:
echo   dist\RobloxAccountManager.exe
echo.
echo You can distribute this single .exe file.
echo Users do NOT need Python installed!
echo.
pause
