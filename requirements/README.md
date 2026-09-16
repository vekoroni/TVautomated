# Python dependencies (pinned)

Interpreter: **Python 3.14** (ACK decision, 16 Sep 2026). Production and tests use the same repository venv.

| File | Contents |
|---|---|
| `runtime-py314.lock.txt` | Exact package versions of the production interpreter `C:\Python314` on 16 Sep 2026 (`pip freeze`), excluding the editable `vanguard` install that pointed outside the repository (`C:\Users\ACKVerissimo\vanguard`). |
| `test.lock.txt` | Test tools (pytest and its dependencies). |

Rebuild the venv (PowerShell, repository root):

```powershell
C:\Python314\python.exe -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements\runtime-py314.lock.txt -r requirements\test.lock.txt
```

Changing a version is a reviewed change: update the lock file, rebuild, run `tests_rebuild`, commit.

The previous Python 3.13 venv was moved to `C:\Users\ACKVerissimo\AVSHUNTER_venv313_backup_20260916` (it contained packages production never had: `arch`, `statsmodels`, `fastparquet`, `polygon-api-client`, `reportlab`, `watchdog`, …). Delete it once the 3.14 venv has run the pipelines successfully.
