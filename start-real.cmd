@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Python 환경이 없습니다. README.md의 설치 단계를 먼저 진행하세요.
  pause
  exit /b 1
)
echo 실제 자동 절전 모드입니다. 5분간 얼굴과 입력이 없으면 컴퓨터가 절전됩니다.
choice /C YN /N /M "실행할까요? [Y/N] "
if errorlevel 2 exit /b 0
start "Desk Guardian" ".venv\Scripts\pythonw.exe" -m src.main --enable-sleep
