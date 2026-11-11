@echo off
REM APIGUARD -- advisor demo. Run from C:\cyberProject:  demo\demo.bat
setlocal
cd /d "%~dp0.."
set PYTHONPATH=src

echo.
echo ==== 1. The contract tests ==================================
python tests\test_normalizer.py
pause

echo.
echo ==== 2. S0 on the VAmPI spec ================================
python demo\run_s0_demo.py
pause

echo.
echo ==== 3. S0 on 12 real APIs from APIs.guru ===================
python -m apiguard.core.normalizer demo\specs\apis_guru_sample -o demo\out\apis_guru_endpoints.jsonl -e demo\out\apis_guru_errors.jsonl --stats
echo.
echo Endpoint records written to demo\out\apis_guru_endpoints.jsonl
pause
endlocal
