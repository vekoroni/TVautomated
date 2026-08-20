@echo off
echo ============================================================
echo AVSHUNTER M&A Cockpit v1.0 - Installation
echo ============================================================
pip install anthropic --break-system-packages --quiet 2>nul || pip install anthropic --quiet
echo Dependencies installed.
schtasks /create /tn "AVSHUNTER_MACockpit_Morning" /tr "python \"%~dp0ma_cockpit_scheduler.py\" morning" /sc daily /st 06:45 /f >nul 2>&1
schtasks /create /tn "AVSHUNTER_MACockpit_Midday"  /tr "python \"%~dp0ma_cockpit_scheduler.py\" midday"  /sc daily /st 12:15 /f >nul 2>&1
schtasks /create /tn "AVSHUNTER_MACockpit_Evening" /tr "python \"%~dp0ma_cockpit_scheduler.py\" evening" /sc daily /st 17:45 /f >nul 2>&1
echo Scheduled: 06:45  12:15  17:45
echo ============================================================
echo Installation complete. Run start.bat to open the cockpit.
echo ============================================================
pause
