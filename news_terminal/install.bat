@echo off
echo ============================================================
echo AVSHUNTER News Terminal v1.3 — Installation
echo ============================================================

echo Installing dependencies...
pip install anthropic --break-system-packages --quiet
if %errorlevel% neq 0 (
    pip install anthropic --quiet
)
echo Dependencies installed.

echo.
echo Setting up Task Scheduler for 3 daily runs...

:: Morning run — 06:30 ET
schtasks /create /tn "AVSHUNTER_NewsTerminal_Morning" /tr "python \"%~dp0news_terminal_scheduler.py\" morning" /sc daily /st 06:30 /f >nul 2>&1
echo   Morning run: 06:30

:: Midday run — 12:00 ET
schtasks /create /tn "AVSHUNTER_NewsTerminal_Midday" /tr "python \"%~dp0news_terminal_scheduler.py\" midday" /sc daily /st 12:00 /f >nul 2>&1
echo   Midday run:  12:00

:: Evening run — 17:30 ET
schtasks /create /tn "AVSHUNTER_NewsTerminal_Evening" /tr "python \"%~dp0news_terminal_scheduler.py\" evening" /sc daily /st 17:30 /f >nul 2>&1
echo   Evening run: 17:30

echo.
echo ============================================================
echo Installation complete.
echo To open the interactive terminal, run:
echo   python news_terminal.py
echo ============================================================
pause
