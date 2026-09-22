"""Provider grammar for v2; local evidence and authority checks remain mandatory."""
import re


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _fixed(value):
    if isinstance(value, dict):
        return _object({key: _fixed(item) for key, item in value.items()})
    if isinstance(value, str):
        value = str(value.value) if hasattr(value, "value") else str(value)
    kind = {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}[type(value)]
    return {"type": kind, "const": value}


def output_schema(contract, catalog, *, detailed=False):
    available = sorted(ref for ref, row in catalog.items() if row["status"] == "AVAILABLE")
    numeric = sorted(ref for ref in available if catalog[ref]["unit"] != "structured_json"
                     and type(catalog[ref]["value"]) in (int, float))
    slots = sorted(set(numeric) | {ref for ref in available
                   if catalog[ref]["unit"] != "structured_json" and catalog[ref]["kind"] == "SCENARIO"})
    prose = {"type": "string", "pattern": r"^[^\d{}]*$"}
    # Escape regex metacharacters only; preserve portable literal punctuation.
    alternatives = "|".join(re.sub(r"([\\.^$|?*+()\[\]{}])", r"\\\1", ref) for ref in slots)
    text = dict(prose)
    if slots:
        text["pattern"] = r"^([^\d{}]|\{\{slot:(" + alternatives + r")\}\})*$"
    # Anthropic's constrained-output grammar accepts minItems only at 0 or 1
    # and does not support maxItems. The catalog-sized slot regex can also
    # exceed its pattern subset. Detailed requests use a portable grammar;
    # local assessment/semantic validation retains the stricter rules.
    provider_text = {"type": "string"} if detailed else text
    provider_summary = {"type": "string"} if detailed else prose
    reference = {"type": "string", "enum": available} if available else {"type": "string", "pattern": "^$"}
    refs = {"type": "array", "items": reference}
    claim = _object({"claim_id": {"type": "string"},
        "claim_type": {"type": "string", "enum": ["OBSERVATION", "INTERPRETATION", "HYPOTHESIS"]},
        "text": provider_text, "supporting_evidence_ids": {**refs, "minItems": 1}, "contradicting_evidence_ids": refs})
    section = _object({"section": {"type": "string", "enum": [s["section"] for s in contract["sections"]]},
        "summary": provider_summary, "claim_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}}})
    fact = _object({"evidence_id": {"type": "string", "enum": numeric} if numeric else {"type": "string", "pattern": "^$"},
        "value": {"type": "number"}, "unit": {"type": "string"}})
    properties = {key: _fixed(value) for key, value in contract.items() if key not in ("claims", "sections", "numeric_facts")}
    properties.update(claims={"type": "array", "items": claim, **({"minItems": 1} if detailed else {})}, sections={"type": "array", "items": section},
                      numeric_facts={"type": "array", "items": fact})
    return _object(properties)
