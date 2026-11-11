@echo off
cd /d "%~dp0"
set PYTHONPATH=src
set LOG=results\sens_log.txt
echo ===== Sensitivity run (older 46-positive key). Leave open. =====
echo started %date% %time% > %LOG%
python experiments\e2_rule_holdout.py --l2-final results\L2_final_v1_two_pass_adjudicated.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
copy /y results\e2.json results\e2_sens_v1key.json >nul
python experiments\e1_accuracy.py --l2-final results\L2_final_v1_two_pass_adjudicated.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
copy /y results\e1.json results\e1_sens_v1key.json >nul
copy /y results\main_run_backup\e1.json results\e1.json >nul
copy /y results\main_run_backup\e2.json results\e2.json >nul
echo finished %date% %time% >> %LOG%
echo ===== FINISHED. Tell Claude. =====
pause
exit /b 0
:failed
echo ===== FAILED. Send last 20 lines of results\sens_log.txt to Claude. =====
pause
