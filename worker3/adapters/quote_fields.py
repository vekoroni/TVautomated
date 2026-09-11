"""Typed underlying NBBO evidence; no option identity inference or trade signal."""
from dataclasses import dataclass, replace
import math

from .native import attach_native_document
from ..domain import ContractError, Observation, canonical, digest, instant, utc


@dataclass(frozen=True, slots=True)
class QuoteFieldResult:
    bundle: object
    status: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def map_underlying_quote(bundle, snapshot):
    # Reuse the native identity/cutoff checks, but don't duplicate document evidence.
    probe = replace(bundle, observations=tuple(o for o in bundle.observations
                                              if o.field != "native_document_lab_signal_book"))
    if not probe.observations:
        probe = bundle
    attach_native_document(probe, snapshot)
    if snapshot.kind != "LAB_SIGNAL_BOOK":
        raise ContractError("underlying quote requires native Lab evidence")
    row = snapshot.payload()["source_document"]["row"]
    def unavailable(reason):
        return QuoteFieldResult(bundle, "UNAVAILABLE", (reason,), ())
    source = row.get("underlying_nbbo_source")
    dataset = row.get("underlying_nbbo_dataset_id")
    if not isinstance(source, str) or not source.strip() or not isinstance(dataset, str) or not dataset.strip():
        return unavailable("MISSING_UNDERLYING_QUOTE_PROVENANCE")
    try:
        observed = utc(row.get("underlying_nbbo_timestamp_utc"))
    except ContractError:
        return unavailable("MISSING_OR_AMBIGUOUS_QUOTE_TIME")
    if instant(observed) > instant(snapshot.captured_at):
        return unavailable("QUOTE_TIME_AFTER_CAPTURE")
    def number(value):
        if type(value) not in (int, float):
            return None
        try:
            return float(value) if math.isfinite(value) else None
        except (OverflowError, ValueError):
            return None
    bid = number(row.get("underlying_nbbo_bid"))
    ask = number(row.get("underlying_nbbo_ask"))
    if bid is None or ask is None:
        return unavailable("MISSING_OR_NONNUMERIC_BID_ASK")
    if bid <= 0 or ask <= 0:
        return unavailable("NONPOSITIVE_UNDERLYING_QUOTE")
    if bid > ask:
        return unavailable("CROSSED_UNDERLYING_QUOTE")
    mid = bid / 2 + ask / 2
    supplied = row.get("underlying_nbbo_mid")
    if supplied not in (None, ""):
        value = number(supplied)
        if value is None or not math.isclose(value, mid, rel_tol=1e-9, abs_tol=0.005):
            return unavailable("SOURCE_MIDPOINT_DOES_NOT_RECONCILE")
    spread_bps = ((ask - bid) / mid) * 10000
    if not math.isfinite(spread_bps):
        return unavailable("NONFINITE_SPREAD")
    values = (("underlying_nbbo_bid", bid, "USD/share", "native_nbbo_mapping_v1"),
              ("underlying_nbbo_ask", ask, "USD/share", "native_nbbo_mapping_v1"),
              ("underlying_nbbo_mid", mid, "USD/share", "bid_ask_midpoint_v1"),
              ("underlying_nbbo_spread_bps", spread_bps, "bps_of_mid", "ask_minus_bid_over_mid_v1"))
    if any(o.field in {v[0] for v in values} for o in bundle.observations):
        raise ContractError("typed underlying quote already present; no overwrite")
    provenance = {"provider": source, "dataset_id": dataset, "native_source": snapshot.source_id,
                  "mapping": "underlying_nbbo_fields_v1"}
    observations = tuple(Observation(
        evidence_id="quote-field:" + digest({"snapshot": snapshot.snapshot_hash, "field": field}),
        field=field, value=value, unit=unit, source_id=canonical(provenance),
        source_hash=snapshot.source_hash, observed_at=observed,
        available_at=snapshot.captured_at, scope="TICKER", ticker=bundle.identity.ticker,
        calculation_version=version) for field, value, unit, version in values)
    result = replace(bundle, observations=bundle.observations + observations)
    return QuoteFieldResult(result, "MAPPED", ("SNAPSHOT_NOT_EXECUTION_APPROVAL",),
                            tuple(o.evidence_id for o in observations))
