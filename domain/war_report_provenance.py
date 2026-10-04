"""WAR report provenance schema and HTML render.

Gap 6 (ACK, 25 Sep 2026): the JSON payload is the single source of truth —
report version, run ID, ticker, thesis ID, exact contract symbol, source
paths/IDs/hashes, observed times, claim classification, missing inputs,
counter-case and "would change if" conditions. The HTML is rendered FROM that
JSON. ``render_war_report_html`` makes zero provider calls: it imports no
broker/provider/network client and touches only the payload already in hand,
so opening a saved report can never trigger a live fetch.

Revision (ACK, 25 Sep 2026, post-acceptance review) — schema bumped to v2.
The v1 payload rendered only a source table, missing inputs and counter-cases;
it omitted the WAR synthesis, the claim timeline, the transmission chain,
contradictions, option economics, the advisory judgment, and the 78-question
registry. All of those are now first-class, versioned fields, and
``render_war_report_html`` renders every one of them from the JSON — nothing
in the HTML is sourced from anywhere except the payload passed in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping, Sequence

WAR_REPORT_SCHEMA_VERSION = "war-report-provenance-v2"


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_name: str
    source_path: str | None
    source_id: str | None
    source_hash: str | None
    observed_at_utc: str | None
    claim_classification: str  # OBSERVED / DERIVED / INFERRED


@dataclass(frozen=True, slots=True)
class CounterCase:
    statement: str
    would_change_if: str


@dataclass(frozen=True, slots=True)
class QaAnswer:
    """One row of the 78-question registry (Section F of the design-baseline artifact)."""
    n: int
    q: str
    s: str        # status, e.g. ok / interp / no
    req: str      # what evidence would be required
    src: str      # source(s) consulted
    obs: str      # observation
    interp: str   # interpretation
    counter: str  # counter-reading
    conf: str     # confidence
    miss: str     # missing inputs for this question
    chg: str      # would change if


@dataclass(frozen=True, slots=True)
class WarReportPayload:
    report_version: str
    run_id: str
    ticker: str
    thesis_id: str
    selected_contract_symbol: str | None
    report_generation_time_utc: str
    intelligence_cutoff_utc: str
    sources: tuple[SourceReference, ...]
    missing_inputs: tuple[str, ...]
    counter_cases: tuple[CounterCase, ...]
    war_synthesis: str
    claim_timeline: Mapping[str, Any]
    transmission_chain: Mapping[str, Any]
    coverage_summary: Mapping[str, Any]
    contradictions: tuple[str, ...]
    option_economics: Mapping[str, Any]
    judgment: Mapping[str, Any]
    qa_registry: tuple[QaAnswer, ...]
    authority: str = "ADVISORY_ONLY"
    schema_version: str = WAR_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version, "run_id": self.run_id,
            "ticker": self.ticker, "thesis_id": self.thesis_id,
            "selected_contract_symbol": self.selected_contract_symbol,
            "report_generation_time_utc": self.report_generation_time_utc,
            "intelligence_cutoff_utc": self.intelligence_cutoff_utc,
            "sources": [asdict(s) for s in self.sources],
            "missing_inputs": list(self.missing_inputs),
            "counter_cases": [asdict(c) for c in self.counter_cases],
            "war_synthesis": self.war_synthesis,
            "claim_timeline": dict(self.claim_timeline),
            "transmission_chain": dict(self.transmission_chain),
            "coverage_summary": dict(self.coverage_summary),
            "contradictions": list(self.contradictions),
            "option_economics": dict(self.option_economics),
            "judgment": dict(self.judgment),
            "qa_registry": [asdict(a) for a in self.qa_registry],
            "authority": self.authority,
            "schema_version": self.schema_version,
        }


def build_war_report_payload(
    *, report_version: str, run_id: str, ticker: str, thesis_id: str,
    selected_contract_symbol: str | None, report_generation_time_utc: str,
    intelligence_cutoff_utc: str, sources: Sequence[SourceReference],
    missing_inputs: Sequence[str], counter_cases: Sequence[CounterCase],
    war_synthesis: str, claim_timeline: Mapping[str, Any],
    transmission_chain: Mapping[str, Any], coverage_summary: Mapping[str, Any],
    contradictions: Sequence[str], option_economics: Mapping[str, Any],
    judgment: Mapping[str, Any], qa_registry: Sequence[QaAnswer],
) -> WarReportPayload:
    return WarReportPayload(
        report_version=report_version, run_id=run_id, ticker=ticker.strip().upper(),
        thesis_id=thesis_id, selected_contract_symbol=selected_contract_symbol,
        report_generation_time_utc=report_generation_time_utc,
        intelligence_cutoff_utc=intelligence_cutoff_utc,
        sources=tuple(sources), missing_inputs=tuple(missing_inputs),
        counter_cases=tuple(counter_cases), war_synthesis=war_synthesis,
        claim_timeline=dict(claim_timeline), transmission_chain=dict(transmission_chain),
        coverage_summary=dict(coverage_summary), contradictions=tuple(contradictions),
        option_economics=dict(option_economics), judgment=dict(judgment),
        qa_registry=tuple(qa_registry),
    )


def _escape(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _kv_value(value: Any) -> str:
    if value is None:
        return "NOT AVAILABLE"
    if isinstance(value, (dict, list)):
        # json.dumps(sort_keys=True) so a nested structure renders identically
        # however its keys happened to be ordered in memory -- a JSON
        # round-trip (dumps(sort_keys=True) then loads) does not preserve the
        # original Python insertion order, so the render must not depend on it.
        return json.dumps(value, sort_keys=True)
    return str(value)


def _kv_table(data: Mapping[str, Any]) -> str:
    # Sorted by key so rendering is deterministic regardless of the payload
    # dict's own insertion order too.
    rows = "".join(
        f"<tr><td>{_escape(k)}</td><td>{_escape(_kv_value(v))}</td></tr>"
        for k, v in sorted(data.items(), key=lambda item: item[0])
    )
    return f"<table border='1'><tr><th>Field</th><th>Value</th></tr>{rows}</table>"


def _render_claim_timeline(timeline: Mapping[str, Any]) -> str:
    def _rows(claims: Sequence[Mapping[str, Any]]) -> str:
        return "".join(
            f"<tr><td>{_escape(c.get('claim_id',''))}</td><td>{_escape(c.get('layer',''))}</td>"
            f"<td>{_escape(c.get('classification',''))}</td>"
            f"<td>{_escape(c.get('source_observed_at_utc',''))}</td>"
            f"<td>{_escape(c.get('report_generation_time_utc',''))}</td>"
            f"<td>{_escape(c.get('statement',''))}</td></tr>"
            for c in claims
        )
    header = "<tr><th>Claim</th><th>Layer</th><th>Classification</th><th>Observed</th><th>Generated</th><th>Statement</th></tr>"
    frozen_rows = _rows(timeline.get("frozen_claims", []))
    additive_rows = _rows(timeline.get("additive_claims", []))
    return (
        f"<h3>Frozen (Evening)</h3><table border='1'>{header}{frozen_rows}</table>"
        f"<h3>Additive (Morning/Live)</h3><table border='1'>{header}{additive_rows}</table>"
    )


def _render_transmission_chain(chain: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{_escape(l.get('stage_from',''))}</td><td>{_escape(l.get('stage_to',''))}</td>"
        f"<td>{_escape(l.get('evidence_state',''))}</td><td>{_escape(l.get('basis',''))}</td>"
        f"<td>{_escape(l.get('source_reference') or 'NOT AVAILABLE')}</td></tr>"
        for l in chain.get("links", [])
    )
    return (
        f"<p>Weakest link: {_escape(chain.get('weakest_link_state',''))} | "
        f"Complete and measured: {_escape(chain.get('chain_complete_and_measured',''))}</p>"
        f"<table border='1'><tr><th>From</th><th>To</th><th>State</th><th>Basis</th>"
        f"<th>Source</th></tr>{rows}</table>"
    )


def _render_coverage_summary(summary: Mapping[str, Any]) -> str:
    # source_coverage is a list of small dicts; rendered as its own table
    # (sorted by source_name) rather than through _kv_table's generic str(v),
    # since a dict's str() repr is order-sensitive and JSON round-tripping
    # does not guarantee nested-dict key order either.
    source_coverage = summary.get("source_coverage", [])
    rows = "".join(
        f"<tr><td>{_escape(e.get('source_name',''))}</td><td>{_escape(e.get('state',''))}</td>"
        f"<td>{_escape(e.get('detail',''))}</td></tr>"
        for e in sorted(source_coverage, key=lambda e: e.get("source_name", ""))
    )
    gaps = ", ".join(sorted(summary.get("coverage_gaps", []))) or "None"
    return (
        f"<p>Ticker: {_escape(summary.get('ticker',''))} | "
        f"Narrative completeness: {_escape(summary.get('narrative_completeness',''))} | "
        f"May render full narrative: {_escape(summary.get('may_render_full_narrative',''))}</p>"
        f"<table border='1'><tr><th>Source</th><th>State</th><th>Detail</th></tr>{rows}</table>"
        f"<p>Coverage gaps: {_escape(gaps)}</p>"
    )


def _render_qa_registry(qa_registry: Sequence[Mapping[str, Any]]) -> str:
    rows = "".join(
        f"<tr><td>{_escape(a.get('n',''))}</td><td>{_escape(a.get('q',''))}</td>"
        f"<td>{_escape(a.get('s',''))}</td><td>{_escape(a.get('conf',''))}</td>"
        f"<td>{_escape(a.get('obs',''))}</td><td>{_escape(a.get('interp',''))}</td>"
        f"<td>{_escape(a.get('counter',''))}</td><td>{_escape(a.get('miss',''))}</td>"
        f"<td>{_escape(a.get('chg',''))}</td></tr>"
        for a in qa_registry
    )
    header = ("<tr><th>#</th><th>Question</th><th>Status</th><th>Confidence</th><th>Observation</th>"
              "<th>Interpretation</th><th>Counter</th><th>Missing</th><th>Would change if</th></tr>")
    return f"<table border='1'>{header}{rows}</table>"


def render_war_report_html(payload: Mapping[str, Any] | WarReportPayload) -> str:
    """Render HTML from an already-built payload. Makes zero provider calls.

    Every section below is sourced only from ``data`` — the payload passed
    in — never from a live call, so opening a saved report is pure.
    """
    data = payload.to_dict() if isinstance(payload, WarReportPayload) else dict(payload)
    sources_html = "".join(
        f"<tr><td>{_escape(s.get('source_name',''))}</td>"
        f"<td>{_escape(s.get('claim_classification',''))}</td>"
        f"<td>{_escape(s.get('observed_at_utc') or 'NOT AVAILABLE')}</td>"
        f"<td>{_escape(s.get('source_path') or s.get('source_id') or 'NOT AVAILABLE')}</td>"
        f"<td>{_escape(s.get('source_hash') or 'NOT AVAILABLE')}</td></tr>"
        for s in data.get("sources", [])
    )
    missing_html = "".join(f"<li>{_escape(m)}</li>" for m in data.get("missing_inputs", []))
    counter_html = "".join(
        f"<li>{_escape(c.get('statement',''))} &mdash; would change if: "
        f"{_escape(c.get('would_change_if',''))}</li>"
        for c in data.get("counter_cases", [])
    )
    contradictions_html = "".join(f"<li>{_escape(c)}</li>" for c in data.get("contradictions", []))

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>WAR Report {_escape(data.get('ticker',''))} {_escape(data.get('run_id',''))}</title>"
        "</head><body>"
        f"<h1>{_escape(data.get('ticker',''))} — WAR Report "
        f"({_escape(data.get('authority',''))})</h1>"
        f"<p>Report version {_escape(data.get('report_version',''))} | "
        f"Run {_escape(data.get('run_id',''))} | "
        f"Thesis {_escape(data.get('thesis_id',''))} | "
        f"Contract {_escape(data.get('selected_contract_symbol') or 'NONE')} | "
        f"Schema {_escape(data.get('schema_version',''))}</p>"
        f"<p>Generated {_escape(data.get('report_generation_time_utc',''))} | "
        f"Intelligence cutoff {_escape(data.get('intelligence_cutoff_utc',''))}</p>"

        f"<h2>WAR Synthesis</h2><p>{_escape(data.get('war_synthesis',''))}</p>"

        f"<h2>Judgment</h2>{_kv_table(data.get('judgment', {}))}"

        f"<h2>Option Economics</h2>{_kv_table(data.get('option_economics', {}))}"

        f"<h2>Claim Timeline</h2>{_render_claim_timeline(data.get('claim_timeline', {}))}"

        f"<h2>Transmission Chain</h2>{_render_transmission_chain(data.get('transmission_chain', {}))}"

        f"<h2>Coverage Summary</h2>{_render_coverage_summary(data.get('coverage_summary', {}))}"

        f"<h2>Contradictions</h2><ul>{contradictions_html or '<li>None recorded</li>'}</ul>"

        f"<h2>Sources</h2><table border='1'><tr><th>Source</th><th>Classification</th>"
        f"<th>Observed</th><th>Path/ID</th><th>Hash</th></tr>{sources_html}</table>"

        f"<h2>Missing inputs</h2><ul>{missing_html or '<li>None recorded</li>'}</ul>"

        f"<h2>Counter-case</h2><ul>{counter_html or '<li>None recorded</li>'}</ul>"

        f"<h2>78-Question Registry</h2>{_render_qa_registry(data.get('qa_registry', []))}"
        "</body></html>"
    )


__all__ = ["WAR_REPORT_SCHEMA_VERSION", "SourceReference", "CounterCase", "QaAnswer",
           "WarReportPayload", "build_war_report_payload", "render_war_report_html"]
