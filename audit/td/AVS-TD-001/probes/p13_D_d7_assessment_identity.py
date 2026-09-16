"""D7 — assessment_id: production ContractAssessment.create vs (a) recompute from production formula, (b) ALG-16 formula;
one-field mutations (economic component -> changes; transport-like field -> unchanged). Five synthetic assessments (0 stored rows)."""
from __future__ import annotations
import hashlib, inspect, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa
sys.path.insert(0, str(ROOT))
import domain.dynamic_options_intelligence as D  # noqa

OUT = AUD / "probes" / "p13_D_d7_assessment_identity.json"


def cj(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def alg16(thesis_id, occ, obs_dataset_id, calc, cutoff):
    return hashlib.sha256(cj({"thesis_id": thesis_id, "occ_symbol": occ, "observation_dataset_id": obs_dataset_id,
                              "calculation_version": calc, "evidence_cutoff_utc": cutoff}).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    res = {"create_signature": str(inspect.signature(D.ContractAssessment.create))}
    entry = list(D.ContractEntryState)[0]; appl = list(D.ModelApplicabilityState)[0]
    res["enum_used"] = [str(entry), str(appl)]
    base_cut = datetime(2026, 9, 10, 20, 0, 0, tzinfo=timezone.utc)
    samples = []
    for i, (tk, side) in enumerate([("PLAB", "C"), ("VIPS", "P"), ("BBW", "P"), ("AAPL", "C"), ("XLE", "P")]):
        kw = dict(family_id=f"fam{i:02d}" * 4, thesis_id=f"{tk}:{'CALL' if side == 'C' else 'PUT'}:2026-09-10:OLM2", run_id="20260911_115904",
                  contract_symbol=f"{tk}261016{side}000{25+i}000", observation_id=f"obs{i}" * 8, entry_state=entry, applicability_state=appl,
                  evidence_cutoff_utc=base_cut + timedelta(minutes=i), input_dataset_ids=[f"ds{i}"], calculation_version="contract-economics-v2",
                  feature_version="f1")
        a = D.ContractAssessment.create(**kw)
        ident = {"family_id": kw["family_id"], "contract_symbol": kw["contract_symbol"], "observation_id": kw["observation_id"],
                 "calculation_version": kw["calculation_version"], "evidence_cutoff_utc": D._iso(kw["evidence_cutoff_utc"])}
        recompute = hashlib.sha256(("DOI_CONTRACT_ASSESSMENT_V1|" + cj(ident)).encode("utf-8")).hexdigest()
        a16 = alg16(kw["thesis_id"], kw["contract_symbol"], kw["observation_id"], kw["calculation_version"], D._iso(kw["evidence_cutoff_utc"]))
        muts = {}
        for field, new in (("observation_id", kw["observation_id"] + "x"), ("calculation_version", "v-other"), ("evidence_cutoff_utc", kw["evidence_cutoff_utc"] + timedelta(seconds=1)),
                           ("contract_symbol", kw["contract_symbol"][:-1] + "5"), ("thesis_id", kw["thesis_id"] + "B"), ("run_id", "20260912_000000"),
                           ("input_dataset_ids", ["other_ds"]), ("feature_version", "f2")):
            k2 = dict(kw); k2[field] = new
            muts[field] = D.ContractAssessment.create(**k2).assessment_id != a.assessment_id
        samples.append({"assessment_id": a.assessment_id, "recompute_production_formula_equal": recompute == a.assessment_id,
                        "alg16_formula_equal": a16 == a.assessment_id, "iso_cutoff": ident["evidence_cutoff_utc"], "mutation_changes_id": muts})
    res["samples"] = samples
    res["summary"] = {"n": len(samples), "production_recompute_equal": sum(s["recompute_production_formula_equal"] for s in samples),
                      "alg16_equal": sum(s["alg16_formula_equal"] for s in samples)}
    # family_id includes run_id -> same thesis/contract/observation in another run gets a different assessment_id
    res["family_identity_source"] = inspect.getsource(D.ContractFamily.create).split("identity = {")[1].split("}")[0]
    with ro_conn("control_plane.sqlite") as c:
        res["stored_assessments"] = c.execute("SELECT COUNT(*) FROM doi_contract_assessments").fetchone()[0]
    dump(res, OUT)
    print(json.dumps(res, indent=1, default=str))
