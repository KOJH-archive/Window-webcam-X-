@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Python environment is missing. Follow README.md first.
  pause
  exit /b 1
)
start "Desk Guardian" ".venv\Scripts\pythonw.exe" -m src.main --dry-run
