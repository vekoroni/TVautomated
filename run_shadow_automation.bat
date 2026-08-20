@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "REPO_ROOT=%%~fI"
if exist "%REPO_ROOT%\pipeline_interpreter" goto repo_ready

set "REPO_ROOT=C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"

:repo_ready
if not exist "%REPO_ROOT%\pipeline_interpreter\automation_v2\lab_batch_cli.py" (
  echo [ERROR] AVSHUNTER repository not found at:
  echo         %REPO_ROOT%
  echo Place this BAT in the repository root or update REPO_ROOT.
  exit /b 2
)

set "MAX_CANDIDATES=%~1"
if not defined MAX_CANDIDATES set "MAX_CANDIDATES=1"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "RUN_ID=%%I"

cd /d "%REPO_ROOT%"

echo ============================================================
echo AVSHUNTER Pipeline Interpreter - attended shadow automation
echo Invocation: shadow-%RUN_ID%
echo Candidates: %MAX_CANDIDATES%
echo Precondition: Webull must already be open on the Chart page.
echo ============================================================
echo.

python -m pipeline_interpreter.automation_v2.lab_batch_cli ^
  --pipeline-outputs pipeline_interpreter\MA_Inputs\pipeline_outputs ^
  --staging-root pipeline_interpreter\MA_Inputs\capture_staging ^
  --output-directory "pipeline_interpreter\automation_v2\deployments\shadow-%RUN_ID%" ^
  --invocation-id "shadow-%RUN_ID%" ^
  --max-candidates %MAX_CANDIDATES% ^
  --execute-shadow-batch ^
  --capture-webull ^
  --confirm-attended-shadow-capture ^
  --run-live-interpreter ^
  --confirm-shadow-live-provider

set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo [COMPLETE] Shadow automation finished successfully.
) else (
  echo [STOPPED] Shadow automation returned exit code %RESULT%.
)
exit /b %RESULT%
