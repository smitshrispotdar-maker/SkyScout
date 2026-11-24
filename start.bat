@echo off
cd /d "%~dp0"
set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
"%PYTHON_CMD%" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. & pause & exit /b 1)
start "" http://127.0.0.1:8000
"%PYTHON_CMD%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
