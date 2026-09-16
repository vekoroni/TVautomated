"""p33 - merge '## State log lines' from finished track files into state_log.csv (append only)."""
import csv, io, os, re
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
ORDER = ["A","B","C","D","E","F","G","H","I","N","M1","M2","M3","M4","M5","M6","M8","M9"]
SL = os.path.join(OUT, "state_log.csv")
existing = open(SL, encoding="utf-8").read()
if not existing.endswith("\n"): existing += "\n"
exist_lines = set(l.strip() for l in existing.splitlines())
exist_rows = set(tuple(r) for r in csv.reader(io.StringIO(existing)))
appended, repaired, skipped = [], [], []
for t in ORDER:
    txt = open(os.path.join(OUT, f"track_{t}.md"), encoding="utf-8").read().splitlines()
    sec, f = [], False
    for l in txt:
        if l.startswith("## State log lines"): f = True; continue
        if f and l.startswith("## "): break
        if f: sec.append(l)
    for l in sec:
        s = l.strip()
        if not s or s.startswith("```") or s.lower().startswith("step,state,n"): continue
        rows = list(csv.reader([s]))
        r = rows[0]
        if len(r) != 5:
            # repair: keep first 4, join remainder into note
            if len(r) > 5: r = r[:4] + [",".join(r[4:])]
            else: r = r + [""] * (5 - len(r))
            repaired.append((t, s))
        if not re.match(rf"^{re.escape(t)}(?![A-Za-z])", r[0]):
            r[0] = f"{t}-{r[0]}"
        buf = io.StringIO(); csv.writer(buf, lineterminator="").writerow(r); out = buf.getvalue()
        if s in exist_lines or out in exist_lines or tuple(r) in exist_rows:
            skipped.append((t, s)); continue
        assert len(next(csv.reader([out]))) == 5
        appended.append(out); exist_lines.add(out); exist_rows.add(tuple(r))
with open(SL, "w", encoding="utf-8", newline="") as fh:
    fh.write(existing + "".join(a + "\n" for a in appended))
# validate the whole file
bad = [i for i, r in enumerate(csv.reader(open(SL, encoding="utf-8"))) if len(r) != 5]
print("appended", len(appended), "skipped_dupe", len(skipped), "repaired", repaired, "bad_rows_in_file", bad)
for a in appended: print(a[:110])
