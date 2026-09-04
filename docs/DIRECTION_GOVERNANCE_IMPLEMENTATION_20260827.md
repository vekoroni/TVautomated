# AVSHUNTER Direction Governance Implementation Record

Date: 2026-08-27  
Contract: `dir_v1.0.0`  
Resolution policy: `strangle_resolution_v1.0.0`

## Outcome

The long-option production path now has one governed direction record (GDR).
Discovery can propose a preliminary side, but Options Intelligence is the only
stage that can commit the governed direction. EOD, Morning, Execution and the
Intelligence Lab consume and validate that record; they cannot independently
re-vote or silently invert it.

Only long `CALL` and `PUT` records may become executable. `STRANGLE` and
`UNRESOLVED` records are retained for audit and are blocked before an option
chain request.

## Implemented controls

1. Discovery ambiguity now emits `UNRESOLVED`, never a default `CALL`.
2. Structural direction uses a closed PreCOR table.
3. Non-directional records require two independent evidence families, a 60%
   winning share and a 20% margin before resolution.
4. Placeholder catalyst bias is excluded when the catalyst layer says
   `NO_CATALYST` or `STRUCTURE_ONLY_NO_CATALYST`.
5. Generated targets, selected contracts, footprint direction and Discovery's
   preliminary hint are excluded from resolution evidence.
6. Options Intelligence writes a complete per-ticker GDR, policy hash and
   `governed_direction_records_<run_id>.jsonl` artifact.
7. EOD consumes the GDR and invalidates any contract/economics selected for a
   different side. It writes `direction_transition_matrix_<run_id>.csv`.
8. Morning validates record hash, policy version, resolution chain, target,
   invalidation and selected-contract side.
9. Execution blocks invalid direction lineage before monetisability or quote
   checks can grant an action.
10. The Lab independently blocks any actionable row that lacks valid lineage.
11. The Morning-to-Lab finalizer reconciles direction fields and hashes exactly
    and requires one uniform direction version for the run.
12. The Lab UI shows the final direction, confirmed/resolved badge, basis,
    confidence and independent-evidence lineage.

## Read-only production replay

Source: run `20260827_103049`, 1,501 Options/Vanguard rows. No APIs were called
and no production artifacts were overwritten.

| Measure | Prior artifact | New governed replay |
|---|---:|---:|
| CALL | 549 | 720 |
| PUT | 418 | 524 |
| STRANGLE | 343 | 151 |
| Missing/UNRESOLVED | 191 | 106 |
| Independently resolved pre-contract | n/a | 93 |
| Non-executable pending direction evidence | n/a | 257 |
| Existing wrong-side contracts that would be invalidated | n/a | 45 |

Among executable governed records, the replay mix is approximately 57.9%
CALL and 42.1% PUT. This is materially less skewed than the old Discovery-led
handoff and is explained by the PreCOR intent distribution rather than an
implicit CALL fallback.

## Verification

- Python compilation: pass for all changed production modules and tests.
- Intelligence Lab JavaScript parsing: pass.
- Focused regression checks: 136 passed.
- Latest-run read-only direction replay: completed.
- Repository virtual environment note: the existing `venv` points to an
  inaccessible WindowsApps Python 3.13 executable. Tests were run with the
  available Python 3.14 runtime and installed project libraries.

## Promotion boundary

The code is implemented in the production repository. A fresh Evening run is
required to generate the new GDR and transition artifacts. The following
Morning run must pass `morning_handoff_summary_<run_id>.json` with:

- `status = PASS`
- `execution_lab_exact_match = true`
- `direction_version_uniform = true`
- zero actionable direction-integrity failures

Until those fresh artifacts exist, the earlier run remains historical evidence
only and must not be represented as having passed the new direction contract.

## Backup

Pre-change files are retained under:

`backups/direction_governance_prechange_20260827/`
