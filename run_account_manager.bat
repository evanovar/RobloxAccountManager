@echo off
title Roblox Account Manager - Console Edition
echo.
echo ============================================
echo   Roblox Account Manager - Console Edition
echo ============================================
echo.
echo Simple console interface
echo.

cd /d "%~dp0"
python roblox_account_manager.py

if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)