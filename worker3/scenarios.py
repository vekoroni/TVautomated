"""Snapshot monitoring predicates, deliberately not execution/confirmation authority."""
from dataclasses import dataclass

from .domain import ContractError, Direction, EvidenceBundle


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    kind: str
    comparator: str
    state: str
    price_evidence_id: str
    level_evidence_id: str
    origin_evidence_id: str
    evidence_hash: str
    authority: str = "ADVISORY_ONLY"
    limitation: str = "Snapshot condition only; not confirmation of a breakout or execution permission."
    calculation_version: str = "price_monitoring_predicate_v1"


def evaluate_price_scenario(bundle: EvidenceBundle, *, kind: str, price_id: str,
                            level_id: str, origin_id: str) -> ScenarioResult:
    if kind not in ("SUPPORTS_THESIS", "CHALLENGES_THESIS"):
        raise ContractError("unknown scenario kind")
    if bundle.identity.direction not in (Direction.CALL, Direction.PUT):
        raise ContractError("directional price scenario requires CALL or PUT")
    expected_level = "confirmation_spot" if kind == "SUPPORTS_THESIS" else "invalidation_spot"
    expected_fields = ("underlying_price", expected_level, "thesis_origin_spot")
    index = {obs.evidence_id: obs for obs in bundle.observations}
    if any(type(ref) is not str or ref not in index for ref in (price_id, level_id, origin_id)):
        raise ContractError("scenario evidence reference missing")
    if len({price_id, level_id, origin_id}) != 3:
        raise ContractError("distinct scenario evidence roles required")
    selected = tuple(index[ref] for ref in (price_id, level_id, origin_id))
    for obs, expected in zip(selected, expected_fields):
        if obs.field != expected or obs.scope != "TICKER":
            raise ContractError("scenario requires the governed underlying-price role, not option premium")
    bullish = bundle.identity.direction == Direction.CALL
    upwards = bullish if kind == "SUPPORTS_THESIS" else not bullish
    comparator = "AT_OR_ABOVE" if upwards else "AT_OR_BELOW"
    base = (kind, comparator, price_id, level_id, origin_id, bundle.evidence_hash)
    if any(obs.status != "AVAILABLE" for obs in selected):
        return ScenarioResult(base[0], base[1], "MISSING_INPUT", *base[2:])
    if any(type(obs.value) not in (int, float) or obs.value <= 0 for obs in selected):
        raise ContractError("scenario prices must be positive numbers, not booleans")
    if len({obs.unit for obs in selected}) != 1 or selected[0].unit not in ("USD/share",):
        raise ContractError("scenario price units must match the explicit supported currency")
    price, level, origin = (obs.value for obs in selected)
    if (upwards and level <= origin) or (not upwards and level >= origin):
        raise ContractError("scenario level is on the wrong side of the thesis origin")
    satisfied = price >= level if upwards else price <= level
    return ScenarioResult(base[0], base[1], "SATISFIED" if satisfied else "NOT_SATISFIED", *base[2:])
