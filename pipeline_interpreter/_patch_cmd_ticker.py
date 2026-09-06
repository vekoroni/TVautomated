"""Patch cmd_ticker in pipeline_interpreter_commands.py to call write_all_outputs_with_junior."""
import sys

TARGET = "pipeline_interpreter_commands.py"

with open(TARGET, "rb") as f:
    raw = f.read()

src = raw.decode("utf-8-sig")

# Find the exact target block â€” lines 774-779 from previous inspection
# run_dir, ts = get_run_dir()
# results = write_all_outputs(response, session, run_dir, ts,
#                              tickers=[ticker], prefix=f"ticker_{ticker.lower()}")
# print(f"\n  Deep dive complete ({int(time.time()-t0)}s)")
# _print_results(results, response)
# return response
#
# This appears inside cmd_ticker (not cmd_intraday which has similar code)
# We know cmd_ticker ends around line 779, followed by def cmd_live around line 783

# Strategy: find the block bounded by the write_all_outputs call and the cmd_live def
old_block = (
    "    run_dir, ts = get_run_dir()\n"
    "    results = write_all_outputs(response, session, run_dir, ts,\n"
    "                                 tickers=[ticker], prefix=f\"ticker_{ticker.lower()}\")\n"
    "    print(f\"\\n  Deep dive complete ({int(time.time()-t0)}s)\")\n"
    "    _print_results(results, response)\n"
    "    return response\n"
    "\n"
    "\n"
    "\n"
    "def cmd_live"
)

new_block = (
    "    run_dir, ts = get_run_dir()\n"
    "    results = write_all_outputs(response, session, run_dir, ts,\n"
    "                                 tickers=[ticker], prefix=f\"ticker_{ticker.lower()}\")\n"
    "\n"
    "    # -- Junior Briefing -- merged into ticker output\n"
    "    try:\n"
    "        from pipeline_interpreter_engine import build_story_prompt\n"
    "        from pipeline_interpreter_outputs import write_all_outputs_with_junior\n"
    "        _story_prompt = build_story_prompt(\n"
    "            ticker=ticker,\n"
    "            pipeline_row=row,\n"
    "            options_data=ticker_options if ticker_options else None,\n"
    "            update_type=\"FULL\",\n"
    "        )\n"
    "        _story_response = call_api(_story_prompt, model=MODEL_DEEP_DIVE)\n"
    "        results = write_all_outputs_with_junior(\n"
    "            main_response=response,\n"
    "            story_response=_story_response,\n"
    "            session=session,\n"
    "            run_dir=run_dir,\n"
    "            ts=ts,\n"
    "            ticker=ticker,\n"
    "            pre_trade_prob_block=_ete_block_t,\n"
    "        )\n"
    "        print(\"  \\u2705 Junior Briefing merged into ticker output\")\n"
    "    except Exception as _je:\n"
    "        print(f\"  \\u26a0  Junior Briefing merge skipped: {_je}\")\n"
    "    # -- End Junior Briefing merge\n"
    "\n"
    "    print(f\"\\n  Deep dive complete ({int(time.time()-t0)}s)\")\n"
    "    _print_results(results, response)\n"
    "    return response\n"
    "\n"
    "\n"
    "\n"
    "def cmd_live"
)

if old_block in src:
    src = src.replace(old_block, new_block, 1)
    print("cmd_ticker edit: APPLIED")
else:
    # Try with CRLF line endings
    old_crlf = old_block.replace("\n", "\r\n")
    if old_crlf in src:
        new_crlf = new_block.replace("\n", "\r\n")
        src = src.replace(old_crlf, new_crlf, 1)
        print("cmd_ticker edit: APPLIED (CRLF)")
    else:
        # Debug: find the write_all_outputs call in cmd_ticker area
        print("NOT FOUND - searching for anchor...")
        lines = src.split("\n")
        for i, l in enumerate(lines):
            if "write_all_outputs(response, session, run_dir, ts," in l:
                print(f"  Found at line {i+1}: {repr(l[:80])}")
                for j in range(i, min(i+10, len(lines))):
                    print(f"  {j+1}: {repr(lines[j])}")
                print()
        sys.exit(1)

# Verify syntax
import ast
try:
    ast.parse(src)
    print("Syntax check: OK")
except SyntaxError as e:
    print(f"Syntax ERROR at line {e.lineno}: {e.msg}")
    lines = src.split("\n")
    for j in range(max(0, e.lineno-4), min(len(lines), e.lineno+3)):
        print(f"  {j+1}: {repr(lines[j])}")
    sys.exit(1)

# Write back preserving UTF-8 BOM
bom = b"\xef\xbb\xbf"
encoded = src.encode("utf-8")
with open(TARGET, "wb") as f:
    f.write(bom + encoded)
print("Written.")

