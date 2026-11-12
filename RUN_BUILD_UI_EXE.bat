@echo off
cd /d "%~dp0"
set LOG=results\ui_exe_log.txt
echo ===== Building apiguard-ui.exe (web UI in one exe). Leave open. =====
echo started %date% %time% > %LOG%
taskkill /f /im apiguard-ui.exe >nul 2>&1
taskkill /f /im APIGUARD.exe >nul 2>&1
timeout /t 2 >nul
python -m pip install pyinstaller >> %LOG% 2>&1
python -m PyInstaller --noconfirm --onefile --name apiguard-ui --paths src --paths . --add-data "demo_ui\index.html;demo_ui" --collect-all xgboost --collect-all shap --hidden-import sklearn.utils._typedefs --hidden-import apiguard.cli --hidden-import demo_ui.app src\apiguard_ui_entry.py >> %LOG% 2>&1
if errorlevel 1 goto failed
copy /y dist\apiguard-ui.exe ..\Demo\APIGUARD.exe >nul
robocopy node_modules ..\Demo\node_modules /E /NFL /NDL /NJH /NJS /NP >nul
robocopy models ..\Demo\models /E /NFL /NDL /NJH /NJS /NP >nul
robocopy config ..\Demo\config /E /NFL /NDL /NJH /NJS /NP >nul
robocopy demo\specs ..\Demo\demo\specs /E /NFL /NDL /NJH /NJS /NP >nul
echo ===== BUILT: ..\Demo\APIGUARD.exe  (double-click it; the whole Demo folder is the app). =====
echo finished %date% %time% >> %LOG%
pause
exit /b 0
:failed
echo ===== BUILD FAILED. Send the last 20 lines of %LOG% to Claude. =====
pause
