@echo off
echo ==========================================
echo AVSHUNTER v3.0 HYBRID - EVENING WORKFLOW
echo ==========================================
echo.

echo STEP 1: Running Discovery Scanner (FRESH DATA)...
python avshunter_discovery_v3_HYBRID.py ^
  --universe data\universe\hybrid_universe_enhanced.csv ^
  --force-update ^
  --progress-every 100

echo.
echo STEP 2: Running Position Tracker...
python position_lifecycle_tracker.py

echo.
echo ==========================================
echo EVENING WORKFLOW COMPLETE
echo ==========================================
pause
