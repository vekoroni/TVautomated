"""p20 — Track M9 field census (DISCOVERY, read-only).

Censuses every artefact the primary run 20260911_115904 wrote (per
probes/p03_artefact_inventory_raw.csv), computes per-field statistics and
resolves producer / consumer file:line by scanning all production python
sources once.  Writes (beside this script):

  p20_M9_field_census.csv         per (artefact, field) row
  p20_M9_artefact_aggregate.csv   per artefact aggregate
  p20_M9_duplicate_pairs.csv      duplicate column pairs per artefact
  p20_M9_decision_reads.csv       (field, file:line) reads inside decision-path ranges
  p20_M9_mtrack_field_map.csv     M1-M5 measurement needs -> existing fields
  p20_M9_packages_representative.csv  the packages/ family representative census
  p20_M9_run.log                  timings / notes

Nothing under data/ is written.  No provider is called.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
RUN = "20260911_115904"
RUN_DIR = os.path.join(ROOT, "data", "output", "runs", RUN)
OUT_DIR = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes")
INVENTORY = os.path.join(OUT_DIR, "p03_artefact_inventory_raw.csv")
LOG = open(os.path.join(OUT_DIR, "p20_M9_run.log"), "w", encoding="utf-8")
T0 = time.time()


def log(msg: str) -> None:
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


# --------------------------------------------------------------------------
# 1. Production python sources (loaded once)
# --------------------------------------------------------------------------
EXCL_DIRS = {
    "tests", "backups", "_attic", "audit", "Archive", "venv", ".venv", "__pycache__",
    ".codex_python313_runtime", ".testdeps", "data", "dropbox", "logs", ".git",
    "_cleanup_holding", "decommissioned", "legacy", "node_modules",
}


def load_sources() -> dict[str, list[str]]:
    src: dict[str, list[str]] = {}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in EXCL_DIRS and not d.startswith(".")]
        for f in fn:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    src[rel] = fh.read().split("\n")
            except Exception:
                pass
    return src


# Decision / authority path ranges (file -> list of (lo, hi) inclusive; None = whole file).
# These are the readers whose reads make a field LOAD_BEARING.
DECISION_RANGES: dict[str, list[tuple[int, int]] | None] = {
    "execution_gate.py": None,
    "contracts/direction_governance.py": [(390, 511)],       # validate_direction_record
    "domain/option_liquidity_execution_guard.py": [(84, 193)],  # evaluate_olm_execution_guard
    "domain/execution_authority.py": None,                    # govern_execution_result / violations
    "morning_gate.py": [(216, 470), (1518, 1890), (2076, 2744)],  # checks + run_gate
    "contracts/opportunity_tier.py": None,
    "contracts/lab_control.py": [(1707, 2382), (3246, 3386)],   # lab verdict + tier/recompute
    "eod_candidate_engine.py": [(443, 730), (850, 1010), (1044, 1300), (1318, 1560), (1950, 3203)],
    "orchestrator/dynamic_dispatcher.py": [(84, 158)],        # resolve_accepted_thesis
    "domain/dynamic_options_ranking.py": None,                # DOI ranking
    "canonical_data/dynamic_options_production.py": None,     # DOI production path
}
# Tighter "minimum set for current decisions" ranges
MINSET_RANGES: dict[str, list[tuple[int, int]] | None] = {
    "execution_gate.py": None,
    "contracts/direction_governance.py": [(390, 511)],
    "domain/option_liquidity_execution_guard.py": [(84, 193)],
    "domain/execution_authority.py": [(147, 292)],
    "morning_gate.py": [(216, 470), (1518, 1890), (2076, 2744)],
    "contracts/opportunity_tier.py": None,
    "contracts/lab_control.py": [(1707, 2382)],
    "eod_candidate_engine.py": [(443, 730), (1206, 1300), (2830, 2900)],  # route/block/status + manifest mask
    "orchestrator/dynamic_dispatcher.py": [(84, 158)],
}


def in_ranges(file: str, line: int, ranges: dict) -> bool:
    if file not in ranges:
        return False
    r = ranges[file]
    if r is None:
        return True
    return any(lo <= line <= hi for lo, hi in r)


QUOTED_RE = re.compile(r"""(["'])([A-Za-z_][A-Za-z0-9_]*)\1""")
ATTR_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\b")
BARE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def index_sources(src: dict[str, list[str]], fields: set[str]):
    """Return occurrence indexes restricted to tokens in `fields`.

    quoted[token] -> list of (file, line, kind) kind in {W, R}
    attr[token]   -> list of (file, line, kind)
    bare_assign[token] -> list of (file, line)
    bare_files[token]  -> set(files)
    """
    quoted: dict[str, list] = defaultdict(list)
    attr: dict[str, list] = defaultdict(list)
    bare_assign: dict[str, list] = defaultdict(list)
    bare_files: dict[str, set] = defaultdict(set)
    for file, lines in src.items():
        for i, text in enumerate(lines, 1):
            s = text.lstrip()
            if s.startswith("#"):
                continue
            for m in QUOTED_RE.finditer(text):
                tok = m.group(2)
                if tok not in fields:
                    continue
                rest = text[m.end():]
                # write contexts: ["tok"] = ..., "tok": ..., setdefault("tok", ...)
                kind = "R"
                if re.match(r"\s*\]\s*=(?!=)", rest):
                    kind = "W"
                elif re.match(r"\s*:(?!=)", rest) and not re.match(r"\s*:\s*[\]\)]", rest):
                    kind = "W"
                elif re.search(r"setdefault\(\s*$", text[: m.start()]):
                    kind = "W"
                quoted[tok].append((file, i, kind))
            for m in ATTR_RE.finditer(text):
                tok = m.group(1)
                if tok not in fields:
                    continue
                rest = text[m.end():]
                kind = "W" if re.match(r"\s*=(?!=)", rest) else "R"
                attr[tok].append((file, i, kind))
            for m in BARE_RE.finditer(text):
                tok = m.group(1)
                if tok not in fields:
                    continue
                bare_files[tok].add(file)
                if text[: m.start()].endswith(".") or text[: m.start()].endswith("'") or text[: m.start()].endswith('"'):
                    continue
                if re.match(r"\s*=(?!=)", text[m.end():]):
                    bare_assign[tok].append((file, i))
    return quoted, attr, bare_assign, bare_files


# --------------------------------------------------------------------------
# 2. Artefact loading
# --------------------------------------------------------------------------
def flatten_json(obj, path: str, store: dict, cap: int = 100000) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten_json(v, f"{path}.{k}" if path else str(k), store, cap)
    elif isinstance(obj, list):
        if obj and all(isinstance(e, dict) for e in obj):
            for e in obj:
                flatten_json(e, path + "[]", store, cap)
        else:
            lst = store.setdefault(path, [])
            if len(lst) < cap:
                lst.append(json.dumps(obj) if obj else None)
    else:
        lst = store.setdefault(path, [])
        if len(lst) < cap:
            lst.append(obj)


def json_to_frame(obj) -> pd.DataFrame:
    store: dict = {}
    flatten_json(obj, "", store)
    # A dict of unequal-length lists -> build as object Series per path
    cols = {}
    for k, v in store.items():
        cols[k] = pd.Series(v, dtype=object)
    df = pd.DataFrame({k: v for k, v in cols.items()})
    return df, {k: len(v) for k, v in store.items()}


def keys_first_1mb(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        chunk = fh.read(1_000_000)
    keys = re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', chunk)
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def load_artefact(rel: str, atype: str):
    """Return (df, n_obs_map or None, note)."""
    p = os.path.join(RUN_DIR, rel)
    size = os.path.getsize(p)
    if atype == "csv":
        df = pd.read_csv(p, low_memory=False)
        return df, None, ""
    if atype == "parquet":
        return pd.read_parquet(p), None, ""
    if atype == "jsonl":
        recs = []
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
        df, nobs = json_to_frame(recs)
        return df, nobs, f"jsonl records={len(recs)}"
    if atype == "json":
        if size > 100_000_000:
            keys = keys_first_1mb(p)
            df = pd.DataFrame({k: pd.Series([], dtype=object) for k in keys})
            return df, {k: 0 for k in keys}, "KEYS_ONLY_FIRST_1MB (file >100MB)"
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            obj = json.load(fh)
        df, nobs = json_to_frame(obj)
        return df, nobs, "json flattened"
    return None, None, "NON_TABULAR"


# --------------------------------------------------------------------------
# 3. Per-field statistics
# --------------------------------------------------------------------------
PCT_TOK = ("pct", "percent", "bps", "percentile")
FRAC_TOK = ("frac", "fraction", "ratio", "prob", "probability", "rate", "share", "weight",
            "delta", "gamma", "theta", "vega", "rho", "iv", "vol", "sigma", "corr", "beta",
            "zscore", "confidence", "conviction", "rr", "kelly")
ABS_TOK = ("price", "spot", "strike", "bid", "ask", "mid", "premium", "usd", "oi", "open_interest",
           "volume", "count", "dte", "days", "sessions", "level", "wall", "flip", "target",
           "invalidation", "stop", "entry", "cost", "notional", "size", "contracts", "qty",
           "minutes", "seconds", "age", "n_", "num_", "atr", "vwap", "poc", "high", "low",
           "close", "open", "gex", "dex")
RATIO_OK_GT1 = ("ratio", "rr", "beta", "zscore", "_z", "kelly", "corr", "rate")  # legit > 1


def name_unit(name: str) -> str:
    n = name.lower()
    parts = set(re.split(r"[^a-z0-9]+", n))
    if any(t in parts or n.endswith("_" + t) or ("_" + t + "_") in n for t in PCT_TOK):
        return "percent"
    if any(t in parts for t in FRAC_TOK) or n.endswith("_iv") or n.startswith("iv_"):
        return "fraction"
    if any(t in parts for t in ABS_TOK) or any(n.startswith(t) for t in ("n_", "num_")):
        return "absolute"
    return "unknown"


def infer_unit(name: str, is_num: bool, lo, hi, n_distinct: int):
    """Return (unit_string, ambiguous_bool, candidates)."""
    if not is_num:
        return "text", False, ""
    nu = name_unit(name)
    if lo is None or hi is None or n_distinct <= 1:
        return nu, False, ""
    n = name.lower()
    straddle_field = any(t in n for t in ("spread", "vol", "move", "iv", "sigma"))
    if straddle_field and lo < 1 < hi and not any(t in n for t in ("_price", "spot", "strike", "dte", "days", "count", "rank", "percentile", "score", "_n")):
        return f"AMBIGUOUS(fraction|percent)", True, "fraction|percent (values straddle 1)"
    if nu == "percent" and -1 <= lo and hi <= 1 and hi != 0:
        return f"AMBIGUOUS(percent|fraction)", True, "percent(name)|fraction(range<=1)"
    if nu == "fraction" and hi > 1 and not any(t in n for t in RATIO_OK_GT1):
        return f"AMBIGUOUS(fraction|percent)", True, "fraction(name)|percent(range>1)"
    if nu == "unknown":
        if -1 <= lo and hi <= 1:
            return "unknown(range<=1)", False, ""
        return "unknown", False, ""
    return nu, False, ""


def col_stats(name: str, s: pd.Series, n_obs: int):
    nn = s.dropna()
    # treat empty strings as null
    if nn.dtype == object:
        nn = nn[nn.astype(str).str.strip() != ""]
    n_nonnull = int(len(nn))
    fill = (n_nonnull / n_obs) if n_obs else float("nan")
    if n_nonnull == 0:
        return dict(n_obs=n_obs, n_nonnull=0, fill_rate=round(fill, 4) if n_obs else "",
                    n_distinct=0, is_constant=False, all_null=True, is_numeric=False,
                    lo="", hi="", mean="", std="", near_zero_variance=False,
                    unit="all_null", unit_ambiguous=False, unit_candidates="", example="", hashkey=None)
    try:
        nd = int(nn.astype(str).nunique())
    except Exception:
        nd = int(pd.Series([json.dumps(x, default=str) for x in nn]).nunique())
    num = pd.to_numeric(nn, errors="coerce")
    is_num = bool(num.notna().sum() >= 0.9 * n_nonnull) and n_nonnull > 0
    lo = hi = mean = std = ""
    nzv = False
    if is_num:
        v = num.dropna().astype(float)
        v = v[np.isfinite(v)]
        if len(v):
            lo, hi = float(v.min()), float(v.max())
            mean, std = float(v.mean()), float(v.std(ddof=0))
            if len(v) >= 2:
                nzv = (std == 0.0) or (mean != 0 and std / abs(mean) < 1e-6)
    unit, amb, cand = infer_unit(name, is_num, lo if is_num and lo != "" else None,
                                 hi if is_num and hi != "" else None, nd)
    is_const = (n_nonnull >= 2 and nd == 1)
    # hash of content for duplicate detection (normalise numerics)
    if is_num:
        key_series = pd.to_numeric(s, errors="coerce").round(10).astype(str)
    else:
        key_series = s.astype(str).str.strip()
    hk = hashlib.md5(pd.util.hash_pandas_object(key_series, index=False).values.tobytes()).hexdigest()
    ex = str(nn.iloc[0])[:40]
    return dict(n_obs=n_obs, n_nonnull=n_nonnull, fill_rate=round(fill, 4), n_distinct=nd,
                is_constant=is_const, all_null=False, is_numeric=is_num,
                lo=lo if lo == "" else round(lo, 6), hi=hi if hi == "" else round(hi, 6),
                mean=mean if mean == "" else round(mean, 6), std=std if std == "" else round(std, 6),
                near_zero_variance=nzv, unit=unit, unit_ambiguous=amb, unit_candidates=cand,
                example=ex, hashkey=hk)


# --------------------------------------------------------------------------
# 4. Main
# --------------------------------------------------------------------------
def main() -> None:
    inv = pd.read_csv(INVENTORY)
    inv = inv[inv["run_id"].astype(str) == RUN].copy()
    log(f"inventory rows for {RUN}: {len(inv)}")

    artefacts: list[tuple[str, str, str]] = []  # (label, relpath, type)
    for _, r in inv.iterrows():
        path, atype = str(r["path"]), str(r["type"])
        if atype.startswith("json(family)"):
            fam = path.split("/")[0] if path.startswith("packages") else "validation_events"
            if path.startswith("packages"):
                files = sorted(glob.glob(os.path.join(RUN_DIR, "packages", "*.package.json")))
                rep = next((f for f in files if os.path.basename(f).startswith("AAPL.")), files[0])
                artefacts.append((f"packages/<TICKER>.package.json [REP={os.path.basename(rep)}; n_files={len(files)}]",
                                  os.path.relpath(rep, RUN_DIR).replace("\\", "/"), "json"))
            else:
                files = sorted(glob.glob(os.path.join(RUN_DIR, "morning_validation", "validation_events", "*.json")))
                rep = files[0]
                artefacts.append((f"morning_validation/validation_events/validation_<id>.json [REP={os.path.basename(rep)}; n_files={len(files)}]",
                                  os.path.relpath(rep, RUN_DIR).replace("\\", "/"), "json"))
        elif atype in ("csv", "parquet", "jsonl", "json"):
            artefacts.append((path, path, atype))
        else:
            artefacts.append((path, path, atype))

    # ---- load artefacts & compute stats -------------------------------
    field_rows: list[dict] = []
    dup_pairs: list[dict] = []
    agg_rows: list[dict] = []
    all_fields: set[str] = set()
    for label, rel, atype in artefacts:
        t = time.time()
        try:
            df, nobs, note = load_artefact(rel, atype)
        except Exception as exc:
            log(f"LOAD FAIL {rel}: {exc}")
            agg_rows.append(dict(artefact=label, type=atype, load_note=f"LOAD_FAIL:{exc}"))
            continue
        if df is None:
            agg_rows.append(dict(artefact=label, type=atype, n_rows="", n_fields=0, load_note=note))
            continue
        n_rows = len(df)
        stats = {}
        for c in df.columns:
            n_obs = nobs.get(c, n_rows) if nobs else n_rows
            if nobs is not None and nobs.get(c, 0) == 0:
                stats[c] = dict(n_obs=0, n_nonnull=0, fill_rate="", n_distinct="", is_constant=False, all_null=False,
                                is_numeric=False, lo="", hi="", mean="", std="", near_zero_variance=False,
                                unit="KEYS_ONLY", unit_ambiguous=False, unit_candidates="", example="", hashkey=None)
                continue
            stats[c] = col_stats(str(c), df[c], n_obs)
        # duplicates within artefact (non-constant, non-null, n_obs>1)
        groups: dict[str, list[str]] = defaultdict(list)
        for c, st in stats.items():
            if st["hashkey"] and not st["is_constant"] and not st["all_null"] and st["n_obs"] > 1:
                groups[st["hashkey"]].append(str(c))
        dup_of = {}
        for hk, cols in groups.items():
            if len(cols) > 1:
                base = cols[0]
                for c in cols[1:]:
                    dup_of[c] = base
                    dup_pairs.append(dict(artefact=label, field=c, duplicate_of=base, n_distinct=stats[c]["n_distinct"]))
        for c in df.columns:
            st = stats[c]
            field_rows.append(dict(artefact=label, field=str(c), **st, duplicate_of=dup_of.get(str(c), "")))
            all_fields.add(str(c).split("[]")[-1].split(".")[-1] if "." in str(c) or "[]" in str(c) else str(c))
        agg_rows.append(dict(artefact=label, type=atype, n_rows=n_rows, n_fields=len(df.columns), load_note=note))
        log(f"loaded {rel}: rows={n_rows} cols={len(df.columns)} {note} ({time.time() - t:.1f}s)")
        del df

    # For JSON paths, the grep token is the leaf key
    def leaf(f: str) -> str:
        f = f.split("[]")[-1]
        return f.split(".")[-1] if f else f

    fields_set = {leaf(r["field"]) for r in field_rows if leaf(r["field"])}
    log(f"unique field tokens to grep: {len(fields_set)} over {len(field_rows)} (artefact,field) rows")

    # ---- source index ---------------------------------------------------
    src = load_sources()
    log(f"production python files loaded: {len(src)} ({sum(len(v) for v in src.values())} lines)")
    quoted, attr, bare_assign, bare_files = index_sources(src, fields_set)
    log("source index built")

    decision_reads_rows: list[dict] = []

    def resolve(tok: str):
        q = quoted.get(tok, [])
        a = attr.get(tok, [])
        ba = bare_assign.get(tok, [])
        writes_q = [(f, l) for f, l, k in q if k == "W"]
        writes_a = [(f, l) for f, l, k in a if k == "W"]
        # lines that carry a write of the same token (passthrough) are not counted as strict reads
        write_lines = {(f, l) for f, l in writes_q}
        reads_all = [(f, l) for f, l, k in q if k == "R"]                       # every quoted read
        reads_q = [(f, l) for f, l in reads_all if (f, l) not in write_lines]  # strict: passthrough lines excluded
        reads_a = [(f, l) for f, l, k in a if k == "R"]
        if writes_q:
            producer = ";".join(f"{f}:{l}" for f, l in writes_q[:3]); pk = "dict_key/subscript"
        elif writes_a:
            producer = ";".join(f"{f}:{l}" for f, l in writes_a[:3]); pk = "attribute"
        elif ba:
            producer = ";".join(f"{f}:{l}" for f, l in ba[:3]); pk = "bare_assign/kwarg"
        else:
            producer, pk = "NO_PRODUCER", ""
        readers = sorted({f for f, _ in reads_q} | {f for f, _ in reads_a})
        strict_readers = sorted({f for f, _ in reads_q})
        # decision-path detection uses every quoted read (a `"k": row.get("k")` alias line inside a
        # verdict resolver IS a decision read); the UNREAD test uses the strict set.
        dec = [(f, l) for f, l in reads_all if in_ranges(f, l, DECISION_RANGES)]
        mins = [(f, l) for f, l in reads_all if in_ranges(f, l, MINSET_RANGES)]
        return dict(producer=producer, producer_kind=pk, n_producer_sites=len(writes_q) or len(writes_a) or len(ba),
                    consumed_by=";".join(readers) if readers else "UNREAD",
                    n_reader_files=len(readers), n_strict_reader_files=len(strict_readers),
                    n_quoted_read_sites=len(reads_q), n_read_sites_incl_passthrough=len(reads_all),
                    n_attr_read_sites=len(reads_a),
                    n_bare_files=len(bare_files.get(tok, ())),
                    decision_reads=";".join(f"{f}:{l}" for f, l in dec[:6]), n_decision_reads=len(dec),
                    minset_reads=";".join(f"{f}:{l}" for f, l in mins[:6]), n_minset_reads=len(mins),
                    _dec=dec, _min=mins)

    cache: dict[str, dict] = {}
    for r in field_rows:
        tok = leaf(r["field"])
        if tok not in cache:
            cache[tok] = resolve(tok)
        res = cache[tok]
        r.update({k: v for k, v in res.items() if not k.startswith("_")})
        r["grep_token"] = tok
        # classification (usage) + unit overlay
        if res["n_decision_reads"] > 0:
            cls = "LOAD_BEARING"
        elif res["consumed_by"] != "UNREAD":
            cls = "ADVISORY_USED"
        elif r["is_constant"] or r["all_null"]:
            cls = "DEAD"
        else:
            cls = "PRODUCED_UNREAD"
        r["classification"] = cls
        r["classification_with_unit_overlay"] = "AMBIGUOUS_UNIT" if r["unit_ambiguous"] else cls
        r["outcome_relation"] = "NOT_TESTABLE"
        r.pop("hashkey", None)

    for tok, res in cache.items():
        for f, l in res["_dec"]:
            decision_reads_rows.append(dict(field=tok, file=f, line=l, in_minset=in_ranges(f, l, MINSET_RANGES),
                                            text=src[f][l - 1].strip()[:160]))

    # ---- write per-field census ---------------------------------------
    cols = ["artefact", "field", "grep_token", "producer", "producer_kind", "n_producer_sites", "n_obs", "n_nonnull",
            "fill_rate", "n_distinct", "is_constant", "all_null", "near_zero_variance", "duplicate_of", "is_numeric",
            "lo", "hi", "mean", "std", "unit", "unit_ambiguous", "unit_candidates", "example", "consumed_by",
            "n_reader_files", "n_strict_reader_files", "n_quoted_read_sites", "n_read_sites_incl_passthrough",
            "n_attr_read_sites", "n_bare_files",
            "decision_reads", "n_decision_reads", "minset_reads", "n_minset_reads", "classification",
            "classification_with_unit_overlay", "outcome_relation"]
    census = pd.DataFrame(field_rows)[cols]
    census.to_csv(os.path.join(OUT_DIR, "p20_M9_field_census.csv"), index=False)
    pd.DataFrame(dup_pairs).to_csv(os.path.join(OUT_DIR, "p20_M9_duplicate_pairs.csv"), index=False)
    pd.DataFrame(decision_reads_rows).sort_values(["file", "line"]).to_csv(
        os.path.join(OUT_DIR, "p20_M9_decision_reads.csv"), index=False)
    census[census["artefact"].str.startswith("packages/")].to_csv(
        os.path.join(OUT_DIR, "p20_M9_packages_representative.csv"), index=False)
    log(f"census rows written: {len(census)}")

    # ---- aggregate per artefact ---------------------------------------
    agg = []
    for a in agg_rows:
        sub = census[census["artefact"] == a["artefact"]]
        n = len(sub)
        fr = pd.to_numeric(sub["fill_rate"], errors="coerce")
        d = dict(a)
        d.update(dict(
            n_fields=n,
            fill_lt_50pct=int((fr < 0.5).sum()), fill_lt_50pct_share=round(float((fr < 0.5).sum()) / n, 4) if n else "",
            all_null=int(sub["all_null"].sum()),
            constants=int(sub["is_constant"].sum()), constants_share=round(float(sub["is_constant"].sum()) / n, 4) if n else "",
            near_zero_variance=int(sub["near_zero_variance"].sum()),
            duplicates=int((sub["duplicate_of"] != "").sum()),
            no_producer=int((sub["producer"] == "NO_PRODUCER").sum()),
            unread=int((sub["consumed_by"] == "UNREAD").sum()), unread_share=round(float((sub["consumed_by"] == "UNREAD").sum()) / n, 4) if n else "",
            ambiguous_unit=int(sub["unit_ambiguous"].sum()),
            LOAD_BEARING=int((sub["classification"] == "LOAD_BEARING").sum()),
            ADVISORY_USED=int((sub["classification"] == "ADVISORY_USED").sum()),
            PRODUCED_UNREAD=int((sub["classification"] == "PRODUCED_UNREAD").sum()),
            DEAD=int((sub["classification"] == "DEAD").sum()),
        ))
        agg.append(d)
    aggdf = pd.DataFrame(agg)
    aggdf.to_csv(os.path.join(OUT_DIR, "p20_M9_artefact_aggregate.csv"), index=False)
    log("aggregate written")

    # ---- M-track need map ----------------------------------------------
    NEEDS = [
        ("M1", "ticker", r"^ticker$"),
        ("M1", "session_date", r"session_date|completed_session|evidence_session|decision_session|^run_date|as_of_date|signal_date|^date$"),
        ("M1", "gics_sector/industry", r"gics|^sector$|industry|sub_industry"),
        ("M1", "usmi_labels", r"usmi|us_money|money_index"),
        ("M1", "forward_prices", r"forward_(price|close|return)|fwd_(price|close|return)|realised_(price|close|return)|realized_(price|close|return)|outcome_price|price_t_plus|close_t\+|forward_realised_return|forward_return"),
        ("M2", "forward_realised_vol", r"forward_realised_vol|forward_realized_vol|realised_vol|realized_vol|garch|forecast_vol|vol_forecast"),
        ("M2", "expected_moves", r"expected_move|budget_move|sigma_move|move_budget"),
        ("M2", "contract_or_atm_iv", r"atm_iv|contract_iv|^iv$|implied_vol|iv_atm|selected_contract_iv|live_iv$|live_contract_iv|entry_iv"),
        ("M2", "realised_prices", r"realised_price|realized_price|outcome_price|forward_close|resolution_price|exit_price"),
        ("M3", "direction", r"^(governed_direction|final_direction|canonical_direction|direction)$"),
        ("M3", "origin_spot", r"thesis_origin_spot|entry_spot|^signal_price$|^underlying_price$|origin_spot"),
        ("M3", "structural_target", r"structural_target|^target_price$|target_spot|reachable_target"),
        ("M3", "invalidation", r"^invalidation_(spot|price|state|level)$|ev3_invalidation_spot"),
        ("M3", "hold", r"hold_sessions|hold_days|planned_hold"),
        ("M3", "decision_session", r"decision_session|thesis_session_date|completed_session|evidence_session_date"),
        ("M3", "preferred_contract", r"preferred_contract|morning_selected_contract_symbol|^contract_symbol$|recommended_contract|selected_contract_symbol"),
        ("M3", "entry_premium", r"entry_premium|selected_contract_(mid|ask|premium)|live_contract_(mid|ask)|^contract_mid$|^contract_ask$|^premium$|entry_price"),
        ("M4", "strike", r"(^|\.)strike$|strike_price"),
        ("M4", "expiry", r"(^|\.)(expiry|expiration|expiration_date|expiry_date)$"),
        ("M4", "bid/ask", r"(^|\.)(bid|ask)$|contract_bid|contract_ask|live_bid|live_ask"),
        ("M4", "greeks", r"(^|\.)(delta|gamma|vega|theta|rho)$|contract_delta|live_delta|contract_gamma|contract_vega|contract_theta"),
        ("M4", "iv", r"(^|\.)iv$|contract_iv|implied_volatility"),
        ("M4", "oi/volume", r"open_interest|(^|\.)oi$|(^|\.)volume$|contract_oi|contract_volume"),
        ("M4", "spot", r"^spot$|underlying_price|spot_price|^current_price$|live_price"),
        ("M4", "sigma_h", r"sigma_h|sigma_horizon|horizon_sigma|sigma_multiple|horizon_vol"),
        ("M5", "thesis_identity", r"thesis_id|trade_idea_id|governed_thesis_id|thesis_book_id|signal_id|decision_id"),
        ("M5", "premium/iv/spot_per_run", r"run_id|pipeline_run_id"),
        ("M5", "quote_timestamps", r"quote_(ts|time|timestamp|asof|as_of|captured)|quote_snapshot|as_of_utc|snapshot_(ts|time|utc)|captured_at|live_.*_(ts|timestamp)|provider_timestamp|observed_at|quote_age"),
    ]
    mrows = []
    for track, need, rx in NEEDS:
        rgx = re.compile(rx, re.I)
        hits = census[census["field"].apply(lambda f: bool(rgx.search(str(f))))]
        if hits.empty:
            mrows.append(dict(track=track, need=need, regex=rx, artefact="", field="", fill_rate="", classification="MISSING_EVERYWHERE"))
        for _, h in hits.iterrows():
            mrows.append(dict(track=track, need=need, regex=rx, artefact=h["artefact"], field=h["field"],
                              fill_rate=h["fill_rate"], n_distinct=h["n_distinct"], unit=h["unit"], classification=h["classification"]))
    pd.DataFrame(mrows).to_csv(os.path.join(OUT_DIR, "p20_M9_mtrack_field_map.csv"), index=False)
    log("mtrack map written")

    # ---- headline numbers ---------------------------------------------
    lab = census[census["artefact"] == "intelligence_lab/lab_signal_book_v3.csv"]
    if len(lab):
        fr = pd.to_numeric(lab["fill_rate"], errors="coerce")
        log(f"LAB BOOK: fields={len(lab)} fill<50%={int((fr < .5).sum())} ({(fr < .5).mean():.1%}) "
            f"constants={int(lab['is_constant'].sum())} ({lab['is_constant'].mean():.1%}) "
            f"unread={int((lab['consumed_by'] == 'UNREAD').sum())} ({(lab['consumed_by'] == 'UNREAD').mean():.1%}) "
            f"ambiguous_unit={int(lab['unit_ambiguous'].sum())} no_producer={int((lab['producer'] == 'NO_PRODUCER').sum())}")
        log("LAB BOOK class counts: " + json.dumps(lab["classification"].value_counts().to_dict()))
    minset = sorted({r["grep_token"] for r in field_rows if r["n_minset_reads"] > 0})
    log(f"MIN-SET (tight decision ranges) distinct field tokens: {len(minset)}")
    decset = sorted({r["grep_token"] for r in field_rows if r["n_decision_reads"] > 0})
    log(f"LOAD_BEARING (broad decision ranges) distinct field tokens: {len(decset)}")
    log(f"TOTAL census rows={len(census)} unique tokens={len(fields_set)} "
        f"class={json.dumps(census['classification'].value_counts().to_dict())}")
    log("done")


if __name__ == "__main__":
    main()
