path = "pipeline_interpreter_system_prompt.txt"
with open(path, encoding="utf-8") as f:
    lines = f.readlines()

total = len(lines)
print(f"Total lines: {total}  (was 848 before append)")

full = "".join(lines)
last_200 = "".join(lines[-200:])

# --- Check 1: append block present and correct ---
append_checks = [
    ("Separator line (triple equals)",      "═══" in last_200),
    ("INTELLIGENCE LAB CONFLICT RULES",     "INTELLIGENCE LAB CONFLICT RULES" in last_200),
    ("LAB_CONTEXT rule",                    "LAB_CONTEXT_" in last_200),
    ("LAB_FIELD_CONFLICTS rule",            "LAB_FIELD_CONFLICTS_" in last_200),
    ("FLAG-severity section",               "FLAG-severity" in last_200),
    ("LAB_NOT_CONFIRMED rule",              "LAB_NOT_CONFIRMED" in last_200),
    ("LAB_ALIGNMENT triage rule",           "LAB_ALIGNMENT block is present" in last_200),
    ("STALE_LAB_DATA warning rule",         "STALE_LAB_DATA" in last_200),
    ("Do not block verdict rule",           "Do not block the verdict" in last_200),
]
print()
print("--- Append verification ---")
all_ok = True
for label, ok in append_checks:
    status = "PASS" if ok else "FAIL"
    if not ok: all_ok = False
    print(f"  {status}  {label}")

# --- Check 2: existing sections intact ---
existing_markers = [
    "AVSHUNTER",
    "Dr. Magnus Vale",
    "Soul of the Chart",
    "EXECUTION PRESCRIPTION",
    "FINAL VERDICT",
    "KILL SWITCH",
    "JUNIOR TRADER LAYER",
    "SECTION_1_MACRO",
    "SECTION_8_VERDICT",
    "WHAT_MAKES_US_ENTER",
    "Status badges",
]
print()
print("--- Existing sections intact ---")
for marker in existing_markers:
    ok = marker in full
    status = "PASS" if ok else "MISSING"
    if not ok: all_ok = False
    print(f"  {status}  {marker}")

# --- Check 3: position ordering ---
lab_pos    = full.rfind("INTELLIGENCE LAB CONFLICT RULES")
junior_pos = full.rfind("JUNIOR TRADER LAYER")
badge_pos  = full.rfind("Status badges")
order_ok   = junior_pos < badge_pos < lab_pos
print()
print("--- Position ordering ---")
print(f"  JUNIOR TRADER LAYER at char:        {junior_pos}")
print(f"  Status badges at char:              {badge_pos}")
print(f"  INTELLIGENCE LAB CONFLICT RULES at: {lab_pos}")
print(f"  Order correct (junior<badges<lab):  {order_ok}")
if not order_ok: all_ok = False

# --- Show last 30 lines so user can read the append ---
print()
print("--- Last 30 lines of file ---")
for i, line in enumerate(lines[-30:], start=total - 29):
    print(f"  {i:4d}  {line}", end="")
if not lines[-1].endswith("\n"):
    print()

print()
print("STEP 9:", "PASS" if all_ok else "FAIL")
