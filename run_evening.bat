@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "REPO_ROOT=%%~fI"
set "VENV_PYTHON=%REPO_ROOT%\venv\Scripts\python.exe"
set "PYTHON_EXE="
set "AVSHUNTER_CANONICAL_DATA_ENABLED=1"
set "AVSHUNTER_CANONICAL_WRITE_THROUGH=1"
set "AVSHUNTER_CDS2_OHLCV_MODE=ACTIVE"
set "AVSHUNTER_HISTORICAL_PRICE_DB=%REPO_ROOT%\data\canonical\historical_prices.sqlite"

if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import pandas, pyarrow" >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=%VENV_PYTHON%"
)

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYTHON_EXE (
      "%%P" -c "import pandas, pyarrow" >nul 2>&1
      if not errorlevel 1 set "PYTHON_EXE=%%P"
    )
  )
)

if not defined PYTHON_EXE (
  echo [ERROR] No usable Python interpreter was found.
  echo         The interpreter must import pandas and pyarrow.
  exit /b 2
)
if not exist "%REPO_ROOT%\intelligent_orchestrator.py" (
  echo [ERROR] Production orchestrator not found:
  echo         %REPO_ROOT%\intelligent_orchestrator.py
  exit /b 2
)

cd /d "%REPO_ROOT%"
echo ============================================================
echo AVSHUNTER - PRODUCTION EVENING WORKFLOW
echo Entrypoint: intelligent_orchestrator.py --evening
echo CDS-2: canonical price write-through ON, reads ACTIVE
echo Python: %PYTHON_EXE%
echo Canonical DB: %AVSHUNTER_HISTORICAL_PRICE_DB%
echo ============================================================

"%PYTHON_EXE%" -c "import os,sys; expected={'AVSHUNTER_CANONICAL_DATA_ENABLED':'1','AVSHUNTER_CANONICAL_WRITE_THROUGH':'1','AVSHUNTER_CDS2_OHLCV_MODE':'ACTIVE'}; bad={k:os.environ.get(k) for k,v in expected.items() if os.environ.get(k)!=v}; print('CDS-2 startup flags: OK' if not bad else 'CDS-2 startup flags: INVALID '+repr(bad)); sys.exit(0 if not bad else 3)"
if errorlevel 1 (
  echo [ERROR] CDS-2 startup contract validation failed.
  exit /b 3
)

if /I "%~1"=="--cds-launcher-self-test" exit /b 0

"%PYTHON_EXE%" "%REPO_ROOT%\intelligent_orchestrator.py" --evening %*
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
  echo [FAILED] Evening workflow returned exit code %RESULT%.
) else (
  echo [COMPLETE] Evening workflow finished successfully.
)
exit /b %RESULT%
