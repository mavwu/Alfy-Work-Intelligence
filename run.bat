@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  copy ".env.example" ".env" >nul
)

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=%CD%\.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" -c "import fastapi, sqlalchemy, uvicorn" >nul 2>nul
if errorlevel 1 (
  echo Backend Python environment is not ready or is broken.
  echo Run setup.bat, then start run.bat again.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Frontend dependencies are missing. Run first-time setup from README before normal startup.
  pause
  exit /b 1
)

start "Alfy Backend" /D "%~dp0backend" cmd /k ""%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Alfy Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo Alfy Work Intelligence is starting.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo.
pause
