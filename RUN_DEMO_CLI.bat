@echo off
cd /d "%~dp0"
set PYTHONPATH=src
set M=models\model_l2plus.json
if exist dist\apiguard.exe (set RUN=dist\apiguard.exe) else (set RUN=python -m apiguard)
if not exist demo\out mkdir demo\out
cls
echo ===== APIGUARD command-line demo: 6 calls, press a key between them =====
echo.
echo CALL 1 of 6: score a vulnerable API (VAmPI). Expected: GATE FAIL.
echo   apiguard scan vampi_openapi3.yaml
echo.
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --format text
echo exit code: %errorlevel%   (1 = block the merge)
pause & cls

echo CALL 2 of 6: a clean, hardened API. Expected: GATE PASS.
echo   apiguard scan clean_openapi3.yaml
echo.
%RUN% scan demo\specs\clean_openapi3.yaml --model %M% --format text
echo exit code: %errorlevel%   (0 = merge allowed)
pause & cls

echo CALL 3 of 6: PULL REQUEST gate. The PR adds one new admin endpoint.
echo Compare with the base branch: only NEW or CHANGED endpoints count.
echo   apiguard scan pr_change.yaml --base clean.yaml
echo.
%RUN% scan demo\specs\pr_change_openapi3.yaml --base demo\specs\clean_openapi3.yaml --model %M% --format text
echo exit code: %errorlevel%   (the two old endpoints are out of scope, the new one blocks the PR)
pause & cls

echo CALL 4 of 6: same PR but WITHOUT a base spec. Every endpoint counts.
echo   apiguard scan pr_change.yaml
echo.
%RUN% scan demo\specs\pr_change_openapi3.yaml --model %M% --format text
echo exit code: %errorlevel%
pause & cls

echo CALL 5 of 6: tune the gate. Same VAmPI file, three settings.
echo   a) threshold 0.95 (very strict score needed)   b) tolerate 20 endpoints (k=20)
echo.
echo --- a) --threshold 0.95
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --threshold 0.95 --format text | findstr /B /C:"endpoints" /C:"GATE"
echo --- b) --max-above 20
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --max-above 20 --format text | findstr /B /C:"endpoints" /C:"GATE"
echo --- default
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --format text | findstr /B /C:"endpoints" /C:"GATE"
pause & cls

echo CALL 6 of 6: machine-readable output for CI. SARIF shows as annotations on the pull request.
echo   apiguard scan vampi_openapi3.yaml --format sarif --out demo\out\apiguard.sarif
echo.
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --format sarif --out demo\out\apiguard.sarif | findstr /B /C:"wrote" /C:"GATE"
%RUN% scan demo\specs\vampi_openapi3.yaml --model %M% --format json --out demo\out\apiguard.json | findstr /B /C:"wrote" /C:"GATE"
dir demo\out\apiguard.sarif demo\out\apiguard.json | findstr /C:"apiguard"
echo.
echo ===== DONE =====
pause
