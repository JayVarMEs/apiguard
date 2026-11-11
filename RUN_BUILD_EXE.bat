@echo off
cd /d "%~dp0"
set LOG=results\exe_log.txt
echo ===== Building apiguard.exe. Leave open. =====
echo started %date% %time% > %LOG%
python -m pip install pyinstaller >> %LOG% 2>&1
python -m PyInstaller --noconfirm --onefile --name apiguard --paths src --collect-all xgboost --collect-all shap --hidden-import sklearn.utils._typedefs --hidden-import apiguard.cli src\apiguard_entry.py >> %LOG% 2>&1
if errorlevel 1 goto failed
echo --- TEST --- >> %LOG%
dist\apiguard.exe scan demo\specs\vampi_openapi3.yaml --model models\model.json >> %LOG% 2>&1
echo exit code %errorlevel% >> %LOG%
echo finished %date% %time% >> %LOG%
echo ===== FINISHED. Tell Claude. =====
pause
exit /b 0
:failed
echo ===== BUILD FAILED. Tell Claude. =====
pause
