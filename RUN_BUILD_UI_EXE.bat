@echo off
cd /d "%~dp0"
set LOG=results\ui_exe_log.txt
echo ===== Building apiguard-ui.exe (web UI in one exe). Leave open. =====
echo started %date% %time% > %LOG%
python -m pip install pyinstaller >> %LOG% 2>&1
python -m PyInstaller --noconfirm --onefile --name apiguard-ui --paths src --paths . --add-data "demo_ui\index.html;demo_ui" --collect-all xgboost --collect-all shap --hidden-import sklearn.utils._typedefs --hidden-import apiguard.cli --hidden-import demo_ui.app src\apiguard_ui_entry.py >> %LOG% 2>&1
if errorlevel 1 goto failed
echo ===== BUILT: dist\apiguard-ui.exe . Double-click it (keep node_modules, models and demo folders in this project). =====
echo finished %date% %time% >> %LOG%
pause
exit /b 0
:failed
echo ===== BUILD FAILED. Send the last 20 lines of %LOG% to Claude. =====
pause
