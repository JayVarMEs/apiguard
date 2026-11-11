@echo off
cd /d "%~dp0"
set PYTHONPATH=src
powercfg /change standby-timeout-ac 0 >nul 2>&1
if not exist results\final_run mkdir results\final_run
set L=results\final_run
echo ===== APIGUARD FINAL RUN. Leave this window open. Logs: %L% =====
echo started %date% %time% > %L%\_status.txt

if not exist results_backup_before_final (
  echo [0] backup results
  xcopy results results_backup_before_final\ /E /I /Q /Y >nul
)

call :step 1_tests            python -m pytest -q
call :step 2_E2               python experiments\e2_rule_holdout.py --l2-final results\L2_final.csv
call :step 3_E1               python experiments\e1_accuracy.py --l2-final results\L2_final.csv
call :step 4_E5               python experiments\e5_ablation_shap.py --l2-final results\L2_final.csv
call :step 5_train            python -m apiguard.model train --l2-final results\L2_final.csv --out models\model.json
call :step 6_E3               python experiments\e3_effort_latency.py --model models\model.json --l2-final results\L2_final.csv
call :step 7_E4               python experiments\e4_external.py --model models\model.json --l3 data\L3_vampi.csv
call :step 8_E6               python experiments\e6_l2_only.py --l2-final results\L2_final.csv --out results
call :step 9_E6_E4            python experiments\e4_external.py --model models\model_l2only.json --l3 data\L3_vampi.csv --out results\e6_out
call :step 10_E7_a            python experiments\e7_more_labels.py --l2-final results\L2_final.csv --out results
call :step 10_E7_b            python experiments\e7_more_labels.py --l2-final results\L2_final.csv --out results
call :step 10_E7_c            python experiments\e7_more_labels.py --l2-final results\L2_final.csv --out results
call :step 11_E8              python experiments\e8_hybrid.py --l2-final results\L2_final.csv --out results
call :step 12_figures         python experiments\make_figures.py
call :step 13_demo_vampi      python -m apiguard scan demo\specs\vampi_openapi3.yaml --model models\model_l2plus.json --format text
call :step 14_demo_crapi      python -m apiguard scan demo\specs\crapi_openapi3.json --model models\model_l2plus.json --format text
call :step 15_demo_clean      python -m apiguard scan demo\specs\clean_openapi3.yaml --model models\model_l2plus.json --format text
call :step 16_exe_install     python -m pip install pyinstaller
call :step 17_exe_build       python -m PyInstaller --noconfirm --onefile --name apiguard --paths src --collect-all xgboost --collect-all shap --hidden-import sklearn.utils._typedefs --hidden-import apiguard.cli src\apiguard_entry.py
call :step 18_exe_test        dist\apiguard.exe scan demo\specs\vampi_openapi3.yaml --model models\model.json

echo finished %date% %time% >> %L%\_status.txt
echo.
type %L%\_status.txt
echo.
echo ===== FINISHED. Send results\final_run\_status.txt to Claude. =====
pause
exit /b 0

:step
for /f "tokens=1,*" %%a in ("%*") do call :run %%a %%b
exit /b 0

:run
set N=%1
echo [%N%] running...
for /f "tokens=1,*" %%x in ("%*") do %%y > "%L%\%N%.log" 2>&1
if errorlevel 1 (echo %N% FAILED >> %L%\_status.txt & echo      FAILED) else (echo %N% ok >> %L%\_status.txt & echo      ok)
exit /b 0
