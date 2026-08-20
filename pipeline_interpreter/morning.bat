@echo off
cd /d "%~dp0"
echo AVSHUNTER Pipeline Interpreter — Morning Validation
echo.
set /p PIPELINE_FILE="Drag pipeline CSV here (or Enter for auto-detect): "
if "%PIPELINE_FILE%"=="" (
    python -c "import sys; sys.path.insert(0,'.'); from pipeline_interpreter_commands import cmd_auto; cmd_auto()"
) else (
    python -c "import sys; sys.path.insert(0,'.'); from pipeline_interpreter_commands import cmd_morning; cmd_morning(r'%PIPELINE_FILE%')"
)
pause
