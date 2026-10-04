"""Event/macro -> sector/peer -> ticker -> selected contract transmission chain.

Gap 3 (ACK, 25 Sep 2026): each link is evidenced link by link. A business-
description match to a sector ("this ticker is a financial, and financials
led today") is a HYPOTHESIS, not measured sector money flow into the ticker.
Each link is recorded as MEASURED, INFERRED or MISSING; a chain is never
rendered complete by silently promoting a description match into a measured
flow claim, and a downstream link cannot be MEASURED when its upstream link
is not.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class LinkEvidenceState(str, Enum):
    MEASURED = "MEASURED"
    INFERRED = "INFERRED"
    MISSING = "MISSING"


_RANK = {LinkEvidenceState.MEASURED: 2, LinkEvidenceState.INFERRED: 1, LinkEvidenceState.MISSING: 0}


class TransmissionStage(str, Enum):
    EVENT_MACRO = "EVENT_MACRO"
    SECTOR_PEER = "SECTOR_PEER"
    TICKER = "TICKER"
    SELECTED_CONTRACT = "SELECTED_CONTRACT"


@dataclass(frozen=True, slots=True)
class TransmissionLink:
    stage_from: str
    stage_to: str
    evidence_state: str
    basis: str
    source_reference: str | None


def classify_sector_link(
    *, has_measured_flow_metric: bool, sector_flow_source_reference: str | None,
    business_description_match_only: bool,
) -> TransmissionLink:
    """Never let a business-description sector match stand in for money flow."""
    if has_measured_flow_metric and sector_flow_source_reference:
        return TransmissionLink(
            TransmissionStage.EVENT_MACRO.value, TransmissionStage.SECTOR_PEER.value,
            LinkEvidenceState.MEASURED.value,
            "measured sector/peer money-flow metric", sector_flow_source_reference,
        )
    if business_description_match_only:
        return TransmissionLink(
            TransmissionStage.EVENT_MACRO.value, TransmissionStage.SECTOR_PEER.value,
            LinkEvidenceState.INFERRED.value,
            "business-description sector match only; no measured flow", None,
        )
    return TransmissionLink(
        TransmissionStage.EVENT_MACRO.value, TransmissionStage.SECTOR_PEER.value,
        LinkEvidenceState.MISSING.value, "no sector linkage evidence available", None,
    )


def classify_ticker_link(
    *, has_ticker_level_metric: bool, ticker_source_reference: str | None,
    sector_link: TransmissionLink,
) -> TransmissionLink:
    """A ticker link cannot be MEASURED on top of an INFERRED or MISSING sector link."""
    if not has_ticker_level_metric or not ticker_source_reference:
        return TransmissionLink(
            TransmissionStage.SECTOR_PEER.value, TransmissionStage.TICKER.value,
            LinkEvidenceState.MISSING.value, "no ticker-level linkage evidence available", None,
        )
    if sector_link.evidence_state == LinkEvidenceState.MEASURED.value:
        return TransmissionLink(
            TransmissionStage.SECTOR_PEER.value, TransmissionStage.TICKER.value,
            LinkEvidenceState.MEASURED.value, "measured ticker-level participation metric",
            ticker_source_reference,
        )
    return TransmissionLink(
        TransmissionStage.SECTOR_PEER.value, TransmissionStage.TICKER.value,
        LinkEvidenceState.INFERRED.value,
        "ticker-level metric present, but upstream sector link is not measured",
        ticker_source_reference,
    )


def classify_contract_link(
    *, selected_contract_symbol: str | None, ticker_link: TransmissionLink,
) -> TransmissionLink:
    if not selected_contract_symbol:
        return TransmissionLink(
            TransmissionStage.TICKER.value, TransmissionStage.SELECTED_CONTRACT.value,
            LinkEvidenceState.MISSING.value, "no selected contract", None,
        )
    state = (
        LinkEvidenceState.MEASURED.value
        if ticker_link.evidence_state == LinkEvidenceState.MEASURED.value
        else LinkEvidenceState.INFERRED.value
    )
    return TransmissionLink(
        TransmissionStage.TICKER.value, TransmissionStage.SELECTED_CONTRACT.value,
        state, "selected contract identity join, inheriting upstream chain state",
        selected_contract_symbol,
    )


def build_transmission_chain(
    *, sector_link: TransmissionLink, ticker_link: TransmissionLink, contract_link: TransmissionLink,
) -> dict[str, Any]:
    links = (sector_link, ticker_link, contract_link)
    weakest = min((LinkEvidenceState(link.evidence_state) for link in links), key=lambda s: _RANK[s])
    return {
        "links": [asdict(link) for link in links],
        "chain_complete_and_measured": weakest is LinkEvidenceState.MEASURED,
        "weakest_link_state": weakest.value,
    }


__all__ = [
    "LinkEvidenceState", "TransmissionStage", "TransmissionLink",
    "classify_sector_link", "classify_ticker_link", "classify_contract_link",
    "build_transmission_chain",
]
