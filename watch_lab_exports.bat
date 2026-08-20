@echo off
setlocal

for %%I in ("%~dp0.") do set "REPO_ROOT=%%~fI"
if exist "%REPO_ROOT%\pipeline_interpreter" goto repo_ready
set "REPO_ROOT=C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"

:repo_ready
if not exist "%REPO_ROOT%\watch_lab_exports.ps1" (
  echo [ERROR] watch_lab_exports.ps1 was not found in:
  echo         %REPO_ROOT%
  echo Copy all three automation files into the AVSHUNTER repository root.
  pause
  exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\watch_lab_exports.ps1" -RepositoryRoot "%REPO_ROOT%" -MaxCandidates 1

set "RESULT=%ERRORLEVEL%"
echo.
echo Watcher stopped with exit code %RESULT%.
pause
exit /b %RESULT%
