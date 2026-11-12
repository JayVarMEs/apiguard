@echo off
cd /d "%~dp0"
if not exist ..\Demo\APIGUARD.exe (
  echo First run: building the app once. This takes a few minutes...
  call RUN_BUILD_UI_EXE.bat
)
if exist ..\Demo\APIGUARD.exe (
  start "" ..\Demo\APIGUARD.exe
) else (
  echo Build failed, starting the Python version instead.
  python demo_ui\app.py
)
