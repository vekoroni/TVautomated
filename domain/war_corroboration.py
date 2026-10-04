"""Corroboration and independence of evidence votes for the WAR report.

Gap 4 (ACK, 25 Sep 2026): correlated outputs sharing one upstream provider or
model are ONE evidence family, not independent votes. Before a state-
transition, hidden-state, order-book or similar field is counted as its own
corroborating vote, its upstream input chain is traced; if two or more fields
trace to the same upstream source, they collapse into a single family and
contribute one vote to any corroboration count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    field_name: str
    value: Any
    upstream_source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceFamily:
    family_id: str
    member_field_names: tuple[str, ...]
    shared_upstream_source_ids: tuple[str, ...]
    independent_vote_count: int = 1


def group_into_evidence_families(signals: Sequence[EvidenceSignal]) -> tuple[EvidenceFamily, ...]:
    """Group signals sharing any upstream source into one non-independent family.

    Two signals with disjoint upstream_source_ids are independent families.
    Any overlap in upstream source merges them; this is deliberately
    conservative — partial upstream sharing is still shared lineage, not
    independent confirmation.
    """
    remaining = list(signals)
    families: list[list[EvidenceSignal]] = []
    while remaining:
        group = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            seed_sources: set[str] = set()
            for member in group:
                seed_sources |= set(member.upstream_source_ids)
            still_remaining = []
            for candidate in remaining:
                if set(candidate.upstream_source_ids) & seed_sources:
                    group.append(candidate)
                    changed = True
                else:
                    still_remaining.append(candidate)
            remaining = still_remaining
        families.append(group)
    result = []
    for index, group in enumerate(families):
        all_sources: set[str] = set()
        for member in group:
            all_sources |= set(member.upstream_source_ids)
        result.append(EvidenceFamily(
            family_id=f"family_{index + 1}",
            member_field_names=tuple(m.field_name for m in group),
            shared_upstream_source_ids=tuple(sorted(all_sources)),
            independent_vote_count=1,
        ))
    return tuple(result)


def corroboration_vote_count(signals: Sequence[EvidenceSignal]) -> int:
    """The number of INDEPENDENT votes, never the raw field count."""
    return len(group_into_evidence_families(signals))


def corroboration_report(signals: Sequence[EvidenceSignal]) -> dict[str, Any]:
    families = group_into_evidence_families(signals)
    return {
        "raw_field_count": len(signals),
        "independent_vote_count": len(families),
        "families": [
            {"family_id": f.family_id, "member_fields": list(f.member_field_names),
             "shared_upstream_source_ids": list(f.shared_upstream_source_ids)}
            for f in families
        ],
        "single_source_conflation_detected": len(signals) > 1 and len(families) == 1,
    }


__all__ = ["EvidenceSignal", "EvidenceFamily", "group_into_evidence_families",
           "corroboration_vote_count", "corroboration_report"]
