@echo off
REM ═══════════════════════════════════════════════════════════════
REM  SID-AI Launcher — Always runs with the pid_env virtual env
REM  Usage: Double-click this file or run from terminal
REM ═══════════════════════════════════════════════════════════════

echo.
echo  ====================================
echo   SID-AI ^| Engineering Intelligence
echo  ====================================
echo.

REM Check if pid_env exists
if not exist "pid_env\Scripts\python.exe" (
    echo [ERROR] pid_env not found! Run: python -m venv pid_env
    echo         Then: pip install -r requirements.txt
    pause
    exit /b 1
)

echo [OK] pid_env found.
echo [INFO] Starting Streamlit with pid_env Python...
echo [INFO] Open http://localhost:8501 in your browser.
echo.

.\pid_env\Scripts\python.exe -m streamlit run app.py --server.port 8501

pause
