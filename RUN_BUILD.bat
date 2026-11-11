@echo off
cd /d "%~dp0"
set PYTHONPATH=src
echo ===== APIGUARD step 1/2: rebuild dataset (scans are cached, ~20 min). Leave this window open =====
powercfg /change standby-timeout-ac 0 >nul 2>&1
set TRIES=0
:again
set /a TRIES+=1
python -m apiguard.dataset build --corpus corpus --out data/dataset --workers 4 --max-rule-rate 0.15
if exist data\dataset.stats.json goto sheets
if %TRIES% GEQ 4 goto failed
echo Build stopped early - restarting (try %TRIES% of 4)...
goto again
:sheets
echo.
echo ===== step 2/2: make the hand-labelling sheets =====
python experiments\make_l2_sheets.py --out results
if errorlevel 1 goto failed
echo.
echo ===== FINISHED. Tell Claude. =====
type data\dataset.stats.json
pause
exit /b 0
:failed
echo.
echo ===== FAILED. Screenshot the red error and send it to Claude. =====
pause
exit /b 1
