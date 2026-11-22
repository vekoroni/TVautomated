"""Saved publication disclosures only. No rank, verdict or execution authority."""
from contracts.required_research_monitor import MONITOR_FIELDS, disclosure
from contracts.research_score_handoff import score_handoff

VERSION='lab_publication_disclosures_v1'
SCORE_FIELDS=('ranking_score_source','ranking_score_100','ranking_score_eod_50')
FIELDS=(*MONITOR_FIELDS,*SCORE_FIELDS)

def publication_disclosures(row,*,as_of=None):
    """Preserve saved packets exactly. Never mix a partial packet with defaults.

    Missing members of a supplied packet are explicitly unknown (None).
    Completely absent packets may use existing policy/score logic for a new
    materialization. Source rows are never modified by this helper.
    """
    out={}
    for fields,derive in ((MONITOR_FIELDS,lambda:disclosure(row,as_of)),
                          (SCORE_FIELDS,lambda:score_handoff(row))):
        if any(k in row for k in fields):
            out.update({k:row[k] if k in row else None for k in fields})
        else:
            values=derive();out.update({k:values[k] for k in fields})
    return out
