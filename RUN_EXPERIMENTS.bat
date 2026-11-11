@echo off
cd /d "%~dp0"
set PYTHONPATH=src
powercfg /change standby-timeout-ac 0 >nul 2>&1
if not exist results mkdir results
if not exist models mkdir models
set LOG=results\run_log.txt
echo ===== APIGUARD experiments. Leave this window open. Log: %LOG% =====
echo started %date% %time% > %LOG%

echo [1/7] E2 rule hold-out (the most important one)
python experiments\e2_rule_holdout.py --l2-final results\L2_final.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [2/7] E1 accuracy vs baselines
python experiments\e1_accuracy.py --l2-final results\L2_final.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [3/7] E5 ablation + SHAP
python experiments\e5_ablation_shap.py --l2-final results\L2_final.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [4/7] train final model
python -m apiguard.model train --l2-final results\L2_final.csv --out models\model.json >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [5/7] E3 effort and latency
python experiments\e3_effort_latency.py --model models\model.json --l2-final results\L2_final.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [6/7] E4 VAmPI external check
python experiments\e4_external.py --model models\model.json --l3 data\L3_vampi.csv >> %LOG% 2>&1
if errorlevel 1 goto failed
echo [7/7] figures
python experiments\make_figures.py >> %LOG% 2>&1
echo.
echo ===== FINISHED. Tell Claude. Results are in the results folder. =====
echo finished %date% %time% >> %LOG%
pause
exit /b 0
:failed
echo.
echo ===== A STEP FAILED. Open results\run_log.txt, copy the last 20 lines, send to Claude. =====
pause
exit /b 1
