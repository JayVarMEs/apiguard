@echo off
REM Builds apiguard.exe (CSS453 requires an exe). Run from the project root in a venv with: pip install -r requirements.txt pyinstaller
REM The exe still needs Node.js + `npm install` on the machine for S1 (Spectral), unless you scan with a model trained with --no-group-e and pass --no-scan.
pyinstaller --onefile --name apiguard --paths src ^
  --collect-all xgboost --collect-all shap --hidden-import sklearn.utils._typedefs ^
  src\apiguard_entry.py
echo.
echo Test:  dist\apiguard.exe scan demo\specs\vampi_openapi3.yaml --model models\model.json
