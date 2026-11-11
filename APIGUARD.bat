@echo off
cd /d "%~dp0"
if not exist dist\apiguard-ui.exe (
  echo First run: building the app once. This takes a few minutes...
  call RUN_BUILD_UI_EXE.bat
)
if exist dist\apiguard-ui.exe (
  start "" dist\apiguard-ui.exe
) else (
  echo Build failed, starting the Python version instead.
  python demo_ui\app.py
)
