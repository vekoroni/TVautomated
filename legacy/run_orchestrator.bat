@echo off
REM ============================================================================
REM AVSHUNTER Enhanced Orchestrator - Quick Run
REM ============================================================================
REM Simple batch file for double-click execution
REM
REM This calls the PowerShell script with default settings

echo ============================================================================
echo AVSHUNTER Enhanced Orchestrator
echo ============================================================================
echo.

REM Check if PowerShell script exists
if not exist "run_enhanced_orchestrator.ps1" (
    echo [ERROR] PowerShell script not found: run_enhanced_orchestrator.ps1
    echo Please ensure both files are in the same directory
    pause
    exit /b 1
)

REM Run PowerShell script
echo [INFO] Starting orchestrator...
echo.

powershell.exe -ExecutionPolicy Bypass -File "run_enhanced_orchestrator.ps1" -Verbose

echo.
echo ============================================================================
echo Press any key to exit...
pause >nul
