@echo off
cd /d "%~dp0"
set PYTHONPATH=src
echo ===== APIGUARD demo: scan two vulnerable-by-design APIs =====
if exist dist\apiguard.exe (set RUN=dist\apiguard.exe) else (set RUN=python -m apiguard)
echo Using: %RUN%
echo (Needs Node.js 20+ and "npm install" done once in this folder, because the scanner step is Spectral.)
echo.
echo ---------- 1/2  VAmPI, 14 endpoints ----------
%RUN% scan demo\specs\vampi_openapi3.yaml --model models\model_l2plus.json --format text
echo gate exit code: %errorlevel%   (1 = FAIL, 0 = PASS; FAIL is the expected answer here)
echo.
pause
echo ---------- 2/2  crAPI, 44 endpoints ----------
%RUN% scan demo\specs\crapi_openapi3.json --model models\model_l2plus.json --format text
echo gate exit code: %errorlevel%
echo.
echo ===== DONE =====
pause
