@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  copy ".env.example" ".env" >nul
)

set "PYTHON_BOOTSTRAP="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  set "PYTHON_BOOTSTRAP=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
) else (
  py -3.12 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_BOOTSTRAP=py -3.12"
)
if "%PYTHON_BOOTSTRAP%"=="" set "PYTHON_BOOTSTRAP=python"

%PYTHON_BOOTSTRAP% -m venv .venv
if errorlevel 1 (
  echo Python could not create a virtual environment. Install Python 3.11 or newer and try again.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt

cd frontend
npm install
cd ..

echo.
echo Setup complete. Use run.bat to start Alfy Work Intelligence.
pause
