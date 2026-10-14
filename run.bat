@echo off
setlocal EnableDelayedExpansion

echo ======================================================================
echo                  AirDrop — Offline File Transfer System               
echo      Local Wi-Fi Peer-to-Peer Transfer (Apple-Inspired Utility)     
echo ======================================================================
echo.

:: 1. Verify Python Installation
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not found in system PATH.
    echo Please install Python 3.11 or newer from https://www.python.org/
    echo Ensure you check the box "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo [*] Detected: %PYTHON_VER%

:: 2. Check or Create Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating isolated virtual environment in .venv ...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [*] Virtual environment created successfully.
)

:: 3. Install / Verify Dependencies
echo [*] Checking dependencies from requirements.txt ...
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install required packages.
    pause
    exit /b 1
)

:: 4. Ensure transfers directory exists
if not exist "transfers" mkdir transfers

:: 5. Determine Local IPv4 Address
for /f "delims=" %%a in ('.\.venv\Scripts\python.exe -c "from app.network import get_local_ip; print(get_local_ip())"') do set LOCAL_IP=%%a

echo.
echo ======================================================================
echo  AirDrop Server Ready!
echo.
echo  Local Laptop URL:    http://localhost:8000
echo  Mobile Access URL:   http://%LOCAL_IP%:8000
echo.
echo  Instructions:
echo  1. Connect your phone to the same Wi-Fi or laptop Mobile Hotspot.
echo  2. Open the Mobile Access URL on your phone or scan the QR code.
echo  3. Enter the 6-digit security pairing code shown on screen.
echo.
echo  Note on Windows Firewall:
echo  If prompted, allow Python access on Private Networks.
echo ======================================================================
echo.

:: 6. Launch Uvicorn Server bound to 0.0.0.0
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

pause
