@echo off
cd /d "%~dp0"
if not exist APIGUARD_APP\APIGUARD.exe (
  echo First run: building the app once. This takes a few minutes...
  call RUN_BUILD_UI_EXE.bat
)
if exist APIGUARD_APP\APIGUARD.exe (
  start "" APIGUARD_APP\APIGUARD.exe
) else (
  echo Build failed, starting the Python version instead.
  python demo_ui\app.py
)
