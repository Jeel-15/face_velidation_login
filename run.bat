@echo off
REM Face Verification Login System - Run Script for Windows

echo.
echo ====================================
echo Face Verification Login System
echo ====================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo Checking dependencies...
pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo.
echo Ready to start server!
echo Opening browser to http://localhost:5000
echo (Press Ctrl+C to stop server)
echo.

timeout /t 2 /nobreak
start http://localhost:5000

python app.py
