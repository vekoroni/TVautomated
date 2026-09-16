"""p33 - one-off patch of p33_artefact_inventory.py: glob-reader credits, generic scans labelled, M9 census not counted."""
p = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001\probes\p33_artefact_inventory.py"
s = open(p, encoding="utf-8").read()
old = '    used = [t for t in ORDER if t in used_md or t in used_probe]\n    label = [t if t in used_md else t + "(probe)" for t in used]\n'
new = '''    # wildcard-glob readers the stem grep cannot see (verified by reading the probe source)
    if path.startswith("ev3_shadow/") and typ in ("csv", "json"): used_probe.add("D")      # p13_D_d8 / d8b: ev3_shadow glob, probability columns/keys
    if re.match(r"horizon/horizon_(1_5d|6_10d|11_20d|blocked)_", path): used_probe.add("M8")  # p28_M8_cells: horizon_*_{rid}.csv
    used = [t for t in ORDER if t in used_md or t in used_probe]
    label = [t if t in used_md else t + "(probe)" for t in used]
    # generic scans: recorded but not counted as examination
    if typ == "csv": label.append("F(scan:header)")                                  # p15_F_04 rglob *.csv header-only
    if typ == "csv" and int(r.size_bytes) <= 60_000_000: label.append("M1(scan:vocab)")  # p21_M1_joinability 4-label text search
    if path in m9d: label.append("M9(scan:field census)")
'''
if old in s:
    s = s.replace(old, new)
s = s.replace('"unexamined_by_test": "TRUE" if not [t for t in used if t != "M9"] else "FALSE"',
              '"unexamined_by_test": "TRUE" if not [t for t in used if t != "M9"] else "FALSE"')
open(p, "w", encoding="utf-8").write(s)
print("patched", new.splitlines()[1][:40] in s)
