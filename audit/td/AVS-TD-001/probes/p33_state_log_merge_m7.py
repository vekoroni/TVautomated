"""p33 - insert track_M7 state log lines after the M6 block (before first M8 line) in state_log.csv; skip existing."""
import csv, io, os, re
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
SL = os.path.join(OUT, "state_log.csv")
lines = open(SL, encoding="utf-8").read().splitlines()
exist = set(tuple(r) for r in csv.reader(lines))
txt = open(os.path.join(OUT, "track_M7.md"), encoding="utf-8").read().splitlines()
sec, f = [], False
for l in txt:
    if l.startswith("## State log lines"): f = True; continue
    if f and l.startswith("## "): break
    if f: sec.append(l.strip())
new, repaired = [], []
for s in sec:
    if not s or s.startswith("```") or s.lower().startswith("step,state,n"): continue
    r = next(csv.reader([s]))
    if len(r) != 5:
        repaired.append(s); r = r[:4] + [",".join(r[4:])] if len(r) > 5 else r + [""] * (5 - len(r))
    if not re.match(r"^M7(?![A-Za-z])", r[0]): r[0] = "M7-" + r[0]
    if tuple(r) in exist: continue
    b = io.StringIO(); csv.writer(b, lineterminator="").writerow(r); new.append(b.getvalue())
idx = next(i for i, l in enumerate(lines) if l.startswith("M8-"))
out = lines[:idx] + new + lines[idx:]
open(SL, "w", encoding="utf-8", newline="").write("\n".join(out) + "\n")
bad = [i for i, r in enumerate(csv.reader(open(SL, encoding="utf-8"))) if len(r) != 5]
print("inserted", len(new), "at line", idx + 1, "repaired", repaired, "bad", bad, "total lines", len(out))
