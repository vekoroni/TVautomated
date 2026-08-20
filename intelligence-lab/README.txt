╔══════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · INTELLIGENCE LAB · SETUP GUIDE                     ║
╚══════════════════════════════════════════════════════════════════╝

PORT: 5002  (5000=Short Squeeze, 5173=Wyckoff Frontend, 8000=Wyckoff Backend, 8001=Position Monitor)

READS FROM:
  C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\{run_id}\

FILES LOADED PER RUN:
  superbrain\superbrain_enriched_{run_id}.csv        → all signals + SB fields
  options\options_intelligence_{run_id}.csv           → greeks, IV, GEX, hold
  options\vanguard_signals_enriched_{run_id}.csv      → L1/L2 auction intelligence
  discovery\discovery_candidates_ultimate_{run_id}.csv → 2000+ discovery tickers
  core_intel\core_intel_dossiers_{run_id}.json        → macro regime + dossiers
  superbrain\superbrain_summary_{run_id}.json         → counts, verdicts, campaigns

═══════════════════════════════════════════════════════════════════

STEP 1 — CREATE THE FOLDER

  Open PowerShell:

    mkdir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab
    mkdir C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab\static


STEP 2 — COPY FILES

  Copy these files to C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab\:
    - intelligence_lab.py
    - requirements.txt

  Copy this file to C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab\static\:
    - index.html


STEP 3 — CREATE VENV AND INSTALL

  cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  pip install -r requirements.txt


STEP 4 — START THE SERVER

  cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab
  .\venv\Scripts\Activate.ps1
  python intelligence_lab.py


STEP 5 — OPEN IN BROWSER

  http://localhost:5002


═══════════════════════════════════════════════════════════════════

DAILY WORKFLOW

  1. Run your evening or premarket pipeline as normal
     python run.py --evening   OR   python run.py --premarket
     (in C:\Users\ACKVerissimo\AVSHUNTER-Intelligence)

  2. The Intelligence Lab auto-detects the new run
     → Click the run selector dropdown to switch runs
     → Or click ⟳ Refresh to reload

  3. All data is served directly from your run output folders
     No file uploads. No manual copy. Fully automatic.


═══════════════════════════════════════════════════════════════════

STARTUP SHORTCUT — add to your daily start batch

  In a new PowerShell window:

    cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\intelligence-lab
    .\venv\Scripts\Activate.ps1
    python intelligence_lab.py


FULL APP PORT MAP:
  5000  Short Squeeze Tracker    (short-squeeze-tracker)
  5002  Intelligence Lab         (intelligence-lab)      ← THIS APP
  5173  Wyckoff Frontend         (wyckoff-project\wyckoff-frontend)
  8000  Wyckoff Backend          (wyckoff-project\wyckoff-backend)
  8001  Position Monitor         (position-monitor)


═══════════════════════════════════════════════════════════════════

TROUBLESHOOTING

  "Cannot reach Flask server"
    → Make sure intelligence_lab.py is running in PowerShell
    → Check port 5002 is not in use: netstat -an | findstr 5002

  "Pipeline directory not found"
    → Check BASE_DIR in intelligence_lab.py matches your install path
    → Default: C:\Users\ACKVerissimo\AVSHUNTER-Intelligence

  "No runs found"
    → Run your pipeline at least once first
    → Check: C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\

  Files missing / showing dashes
    → Some fields depend on all pipeline phases completing
    → Options data requires Phase 9 (options intelligence) to have run
    → Discovery data requires avshunter_discovery_ULTIMATE.py to have run
