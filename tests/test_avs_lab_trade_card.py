"""Lab trade card (ACK 2 Oct 2026): "the objective is for the trader to view the trade card, make
an informed decision then run the interpreter instead of viewing the output folder".

Business rules:
- The book carries the decision fields from the 2 Oct fixes (reachable target and R:Rs,
  governance verdict, GO eligibility); a field the book does not carry cannot be shown.
- The trade card is the default view of a ticker and answers eight questions, one field per fact.
- The card runs the Interpreter for that ticker through the existing advisory desk flow
  (paid-request confirmation, run-bound report shown in the Lab) and opens saved reports.
Assessment: Enhancements/assessment/AVS_LAB_FIELD_ASSESSMENT_20261002/.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row

ROOT = Path(__file__).resolve().parents[1]
NEW_DECISION_FIELDS = ("target_reachable", "target_reachable_state", "target_reach_ratio", "rr_options_reachable",
                       "rr_underlying_reachable", "rr_basis", "target_3r_scenario", "governance__open_contract",
                       "governance__verdict", "governance__reason", "trigger_go_eligible")


def test_book_schema_carries_the_new_decision_fields():
    for field in NEW_DECISION_FIELDS:
        assert field in FINAL_BOOK_FIELDS, field


def test_book_row_passes_the_new_decision_fields_through():
    sig = {"ticker": "XLU", "direction": "PUT", "target_reachable": 37.2, "rr_options_reachable": 0.72,
           "rr_underlying_reachable": 0.49, "governance__verdict": "HOLD", "trigger_go_eligible": True}
    row = opportunity_book_row(sig, "RUN", 1)
    assert row["target_reachable"] == 37.2 and row["rr_options_reachable"] == 0.72
    assert row["rr_underlying_reachable"] == 0.49 and row["governance__verdict"] == "HOLD"
    assert row["trigger_go_eligible"] is True


def test_trade_card_is_the_default_modal_view_and_loads_its_script():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert '<script src="/static/trade-card.js"></script>' in html
    assert "switchMTab('card',this)" in html and 'id="mp-card"' in html
    assert 'class="mtab active" onclick="switchMTab(\'card\',this)"' in html
    assert 'class="mpane active" id="mp-card"' in html
    assert "renderTradeCard(s," in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_trade_card_answers_the_eight_questions_and_runs_the_interpreter():
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const s = {ticker:'XLU', direction:'PUT', thesis_category:'Phase B · no event on the PUT side; opposing Failed Upthrust Continuation (detected, 1mo)',
  thesis_structure_alignment:'OPPOSING_ONLY', trigger_primary:'VOL_COMPRESSION_IV_RICH', trigger_quality:'SINGLE',
  invalidation_price:44.65, target_price:null, target_reachable:37.2, rr_options_reachable:0.72, rr_underlying_reachable:0.49,
  contract_symbol:'XLU270115P00040000', contract_bid:1.55, contract_ask:1.72, contract_delta:-0.4567, ivp_label:'EXPENSIVE',
  lab_verdict:'GO', usmi_sector_alignment:'ALIGNED', call_wall:40, put_wall:25, gamma_flip:38.23, signal_price:39.71};
const html = renderTradeCard(s);
const questions = ['What and which side','Why now','Where wrong','How long','Which contract','Context','Decision state','Can I trust the data'];
const missing = questions.filter(q => !html.includes(q));
console.log(JSON.stringify({missing, interp: html.includes('tradeCardRunInterpreter(') && html.includes('tradeCardSavedReports('),
  rich: html.includes('IV rich'), reach: html.includes('37.2'), opposing: html.includes('OPPOSING_ONLY'),
  callWall: html.includes('overhead resistance')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {"missing": [], "interp": True, "rich": True, "reach": True, "opposing": True, "callWall": True}


def test_opening_a_ticker_activates_the_trade_card_not_the_overview():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    body = html[html.index("function openModal("):html.index("function closeModal()")]
    assert "document.getElementById('mp-card').classList.add('active')" in body
    assert "document.getElementById('mp-overview').classList.add('active')" not in body


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_fields_are_tiered_evidence_drawer_and_audit():
    """Assessment 2 Oct: 48% of book columns carry no row-specific information. The card shows the
    decision; other informative fields go to a collapsed evidence drawer grouped by family; constant,
    duplicate and lineage fields go to a hidden audit tier; always-empty fields are listed for tracing."""
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const rows = [
  {ticker:'A', direction:'CALL', final_direction:'CALL', wyckoff_score:'61', layer2__edge_quality:'WEAK', doi_rank:'3',
   forecast_authority:'ADVISORY_ONLY', calc_version:'v1', empty_field:'', payload_sha256:'aa', dummy_const:'X'},
  {ticker:'B', direction:'PUT', final_direction:'PUT', wyckoff_score:'48', layer2__edge_quality:'NONE', doi_rank:'7',
   forecast_authority:'ADVISORY_ONLY', calc_version:'v1', empty_field:'', payload_sha256:'bb', dummy_const:'X'},
];
const p = tcProfile(rows);
const html = renderEvidenceTiers(rows[0], p);
console.log(JSON.stringify({
  ev: p.evidence.sort(), dup: p.duplicateOf, constant: p.constant.sort(), lineage: p.lineage.sort(), empty: p.empty,
  details: (html.match(/<details/g) || []).length >= 2, auditClosed: html.includes('<details class="tc-audit">'),
  groups: html.includes('Wyckoff') && html.includes('Vanguard') && html.includes('DOI')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["ev"] == ["doi_rank", "layer2__edge_quality", "wyckoff_score"]          # card fields (ticker, direction) excluded
    assert r["dup"] == {"final_direction": "direction"}
    assert r["constant"] == ["dummy_const"]
    assert r["lineage"] == ["calc_version", "forecast_authority", "payload_sha256"]
    assert r["empty"] == ["empty_field"]
    assert r["details"] and r["auditClosed"] and r["groups"]


def test_the_modal_passes_the_run_profile_to_the_card():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "renderTradeCard(s, tcProfileFor(ALL_SIGS, RUN_DATA && RUN_DATA.run_id))" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_quote_row_states_age_feed_and_requote_not_a_bare_stale():
    """N3 (3 Oct 2026): quotes are always old by design (delayed feed); the card says how old the quote
    was at the Morning check and that it must be re-quoted at the broker, never a bare STALE or 'current'."""
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const s = {ticker:'SOFI', direction:'PUT', quote_freshness:'STALE', current_quote_timestamp_utc:'2026-10-02T16:36:58Z',
  execution_viability_quote_raw_age_seconds:1302.8, execution_viability_quote_feed_state:'DELAYED_PROVIDER_FEED'};
const html = renderTradeCard(s);
console.log(JSON.stringify({mins: html.includes('22 min old'), feed: html.includes('delayed feed'),
  requote: html.includes('re-quote at broker'), bare: />STALE ·/.test(html)}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"mins": True, "feed": True, "requote": True, "bare": False}


def test_trade_setup_does_not_call_a_delayed_quote_current():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "A current, executable quote is available" not in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_card_discloses_earnings_against_the_hold_and_expiry():
    """Earnings disclosure (ACK 3 Oct 2026): shown in 'How long', never as a catalyst verdict; unknown says so."""
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const known = renderTradeCard({ticker:'SOFI', direction:'PUT', earnings_state:'SCHEDULED',
  earnings_disclosure:'Earnings 2026-10-27 (before open): 17 sessions away, inside the 20-session hold, before the 2026-12-18 expiry. Gap and IV-crush risk; disclosure only.'});
const unknown = renderTradeCard({ticker:'XLF', direction:'PUT', earnings_state:'UNKNOWN', earnings_disclosure:'Earnings date unknown (HTTP_503); check before entry.'});
const legacy = renderTradeCard({ticker:'AAA', direction:'CALL'});
console.log(JSON.stringify({known: known.includes('17 sessions away') && known.includes('Earnings'),
  unknown: unknown.includes('Earnings date unknown'), legacy: legacy.includes('earnings not checked in this run')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"known": True, "unknown": True, "legacy": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_card_shows_the_anticipated_move_not_rr():
    """Anticipated move (ACK 3 Oct 2026): R:R leaves the card (audit tier only); the invalidation is the thesis
    exit; the card answers how far (level, basis, evidence), how long (q50/q80) and does it pay (coverage, value)."""
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const s = {ticker:'SOFI', direction:'PUT', invalidation_price:19.495, rr_options_reachable:0.72, target_price:4.875,
  target_price_source:'TARGET_3R', anticipated_move_state:'ESTIMATED', anticipated_level:14.2, anticipated_level_basis:'STRUCTURAL',
  anticipated_move_pct:10.8, anticipated_structural_definition:'PRIOR_SWING_LOW', anticipated_p_outcome_by_limit:0.41,
  anticipated_evidence_n:412, anticipated_sessions_q50:6, anticipated_sessions_q80:14,
  anticipated_time_basis:'DURATION_EVIDENCE:1d:OUTCOME:n=412', anticipated_move_coverage:1.2,
  anticipated_breakeven_move_pct:8.98, anticipated_value_multiple_q50:1.35, anticipated_value_multiple_q80:1.21,
  anticipated_stress_basis:'q80 path (14 sessions)'};
const html = renderTradeCard(s);
const old = renderTradeCard({ticker:'XLF', direction:'PUT', target_reachable:37.2});
console.log(JSON.stringify({exit: html.includes('Thesis exit'), level: html.includes('14.20') && html.includes('STRUCTURAL'),
  time: html.includes('6 / 14 sessions'), pays: html.includes('1.20') && html.includes('1.35'),
  noRR: !html.includes('R:R option'), no3R: !html.includes('TARGET_3R'),
  old: old.includes('anticipated move not computed in this run') && old.includes('37.20')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"exit": True, "level": True, "time": True, "pays": True,
                                                              "noRR": True, "no3R": True, "old": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_stop_based_rr_fields_sit_in_the_audit_tier_as_legacy():
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const rows = [{ticker:'A', rr_options:'3.1', rr_underlying:'0.4', target_3r_scenario:'4.8', structural_target:'4.8', wyckoff_score:'61'},
              {ticker:'B', rr_options:'0.9', rr_underlying:'1.2', target_3r_scenario:'60', structural_target:'60', wyckoff_score:'48'}];
const p = tcProfile(rows);
const html = renderEvidenceTiers(rows[0], p);
console.log(JSON.stringify({legacy: p.legacy.sort(), evidence: p.evidence, label: html.includes('Legacy stop-based R:R')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["legacy"] == ["rr_options", "rr_underlying", "structural_target", "target_3r_scenario"]
    assert r["evidence"] == ["wyckoff_score"] and r["label"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_card_warns_when_the_contract_expires_before_the_anticipated_time():
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeCard({ticker:'TW', direction:'CALL', anticipated_move_state:'ESTIMATED', anticipated_level:140.9,
  anticipated_sessions_q50:115, anticipated_sessions_q80:180, anticipated_move_coverage:7.27, anticipated_breakeven_move_pct:4.96,
  anticipated_time_fit:'CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME'});
console.log(JSON.stringify({warn: html.includes('contract expires before the median anticipated time')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"warn": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_detected_event_shows_activation_time_separately():
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const html = renderTradeCard({ticker:'SOFI', direction:'PUT', anticipated_move_state:'ESTIMATED', anticipated_level:15.21,
  anticipated_sessions_q50:9, anticipated_sessions_q80:24, thesis_event_state:'DETECTED', thesis_event_timeframe:'1d',
  thesis_activation_q50_bars:2, thesis_activation_q80_bars:5, thesis_p_activation_by_limit:0.61});
console.log(JSON.stringify({act: html.includes('activation (trigger) typically within 2 / 5 bars (1d)')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"act": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_card_states_whether_the_move_pays():
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const no = renderTradeCard({ticker:'X', direction:'PUT', anticipated_move_coverage:0.4, anticipated_breakeven_move_pct:9,
  anticipated_value_multiple_q50:0.7, anticipated_pays_state:'DOES_NOT_PAY_AT_ANTICIPATED_TIME'});
const yes = renderTradeCard({ticker:'Y', direction:'PUT', anticipated_move_coverage:0.5, anticipated_breakeven_move_pct:9,
  anticipated_value_multiple_q50:1.25, anticipated_pays_state:'PAYS'});
console.log(JSON.stringify({no: no.includes('does not pay at the anticipated time'), yes: yes.includes('pays at the anticipated time')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"no": True, "yes": True}


def test_book_carries_the_trade_lane():
    from domain.structure_behaviour.trade_lane import TRADE_LANE_FIELDS
    for field in TRADE_LANE_FIELDS:
        assert field in FINAL_BOOK_FIELDS, field
    row = opportunity_book_row({"ticker": "L", "trade_lane": "B", "trade_lane_basis": "EARLY_ENTRY_MEASURED",
                                "price_band": "ABOVE_500"}, "RUN", 1)
    assert row["trade_lane"] == "B" and row["price_band"] == "ABOVE_500"


def test_card_states_the_lane_and_warns_on_early_entry():
    # ACK 4 Oct 2026: lanes never mixed; lane B shows its failure rate and the payoff it needs.
    script = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    probe = script + """
const a = renderTradeCard({ticker:'A', direction:'CALL', trade_lane:'A', trade_lane_setup:'1d|SOS -> LPS continuation|ACTIVATED',
  trade_lane_hit_original:0.726, trade_lane_hit_holdout:0.678});
const b = renderTradeCard({ticker:'B', direction:'CALL', trade_lane:'B', trade_lane_setup:'1d|Spring Candidate|DETECTED',
  trade_lane_hit_original:0.74, trade_lane_hit_holdout:0.76, trade_lane_required_multiple:1.35});
const c = renderTradeCard({ticker:'C', direction:'PUT', trade_lane:'C', trade_lane_basis:'NO_TESTED_EVIDENCE'});
console.log(JSON.stringify({a: a.includes('Lane A') && a.includes('trade now'),
  b: b.includes('Lane B') && b.includes('about 1 in 4 fail') && b.includes('1.35'),
  c: c.includes('Lane C') && c.includes('watch') && c.includes('NO_TESTED_EVIDENCE')}));
"""
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"a": True, "b": True, "c": True}
