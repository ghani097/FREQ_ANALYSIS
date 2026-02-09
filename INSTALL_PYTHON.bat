@echo off
REM Installation script for EEG Frequency Analysis Tool - Python Version

echo ================================================================
echo   EEG Frequency Analysis Tool - Python Installation
echo ================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed!
    echo Please download and install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python is installed
python --version
echo.

echo Installing required packages...
echo This may take a few minutes...
echo.

REM Install packages
python -m pip install --upgrade pip
python -m pip install -r requirements_python.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed!
    echo.
    echo Try installing manually:
    echo   pip install mne numpy scipy matplotlib seaborn PyQt6 pandas scikit-learn
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   Installation Complete!
echo ================================================================
echo.
echo To launch the GUI, run:
echo   python py_gui_main.py
echo.
echo Or double-click: RUN_GUI.bat
echo.
pause
