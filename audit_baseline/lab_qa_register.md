# Intelligence Lab — Quant QA Audit Register

Generated 2026-08-01 18:50 UTC by `lab_qa_audit.py` v1.0

READ-ONLY analysis of exported CSVs. No source code was inspected, so every finding below is an **observation about the data**. Causes are unverified and require source review.

## Summary

| Files | P0 | P1 | P2 | Info |
|---|---|---|---|---|
| 1 | **5** | 13 | 1 | 5 |

**Severity rubric** — P0: can make an unsound trade appear sound, or silently discard a sound one. P1: removes a safety signal or makes a defect undiagnosable. P2: robustness, no correctness effect. INFO: characterisation, no defect asserted.

## `avshunter_signals_20260731_083130_2026-07-31_1640.csv`

96 rows x 64 columns

### LABQA-001 — [P0] Eligibility fields not present in export

**Class:** `SCHEMA`  
**Confidence:** 99%  

Documented trade eligibility requires live_data_mode=LIVE and immutable identity requires trade_idea_id. Neither is exported.

**Consequence.** The documented eligibility condition cannot be enforced from this file. Identity cannot be bound to a trade idea.

<details><summary>Evidence</summary>

```json
{
  "absent": [
    "live_data_mode",
    "trade_idea_id"
  ]
}
```

</details>

### LABQA-002 — [P0] 15 column(s) are 100% null

**Class:** `DEAD_COLUMN`  
**Confidence:** 99%  

Columns present in the header but empty on every row.

**Consequence.** Veto/EIL/reason fields are empty, so a consumer checking Vetoes_Count == 0 as a safety condition passes every row unconditionally.

<details><summary>Evidence</summary>

```json
{
  "dead_columns": [
    "Horizon_Action",
    "Horizon_Pressure",
    "Horizon_Source",
    "Trigger_Price",
    "Trigger_Primary",
    "Trigger_Quality",
    "Trigger_Codes",
    "Days_To_Trigger",
    "Vetoes",
    "Vetoes_Count",
    "EIL_Verdict",
    "EIL_Raw_Verdict",
    "EIL_Composite",
    "MV_Drift_Pct",
    "Verdict_Reason"
  ],
  "safety_fields_dead": [
    "Vetoes",
    "Vetoes_Count",
    "EIL_Verdict",
    "EIL_Raw_Verdict",
    "EIL_Composite",
    "Verdict_Reason"
  ],
  "row_count": 96
}
```

</details>

### LABQA-008 — [P0] R:R reported as 0 where it is computable and positive

**Class:** `SILENT_ZERO`  
**Confidence:** 95%  

13 row(s) report RR=0 while the exported strike/target/premium give a positive R:R.

**Consequence.** Any 'RR > 0' filter discards these candidates. If the skew is directional, candidate selection acquires a directional bias that comes from a data defect, not from the strategy.

<details><summary>Evidence</summary>

```json
{
  "affected_rows": 13,
  "zeroed_by_direction": {
    "CALL": 13,
    "PUT": 0
  },
  "computable_by_direction": {
    "CALL": 31,
    "PUT": 34
  },
  "zeroed_pct_by_direction": {
    "CALL": 41.9,
    "PUT": 0.0
  },
  "directional_skew_pp": 41.9,
  "examples": [
    {
      "Ticker": "JPM",
      "Instrument": "LONG_CALL",
      "Strike": 355.0,
      "Structural_Target": 371.9100000000001,
      "Premium_Mid": 5.75,
      "RR": 0.0,
      "RR_computable": 1.941
    },
    {
      "Ticker": "SCHW",
      "Instrument": "LONG_CALL",
      "Strike": 105.0,
      "Structural_Target": 110.59,
      "Premium_Mid": 2.16,
      "RR": 0.0,
      "RR_computable": 1.588
    },
    {
      "Ticker": "MT",
      "Instrument": "DEBIT_SPREAD_CALL",
      "Strike": 70.0,
      "Structural_Target": 73.5,
      "Premium_Mid": 2.975,
      "RR": 0.0,
      "RR_computable": 0.176
    },
    {
      "Ticker": "HOOD",
      "Instrument": "LONG_CALL",
      "Strike": 90.0,
      "Structural_Target": 105.32,
      "Premium_Mid": 5.375,
      "RR": 0.0,
      "RR_computable": 1.85
    },
    {
      "Ticker": "NUE",
      "Instrument": "LONG_CALL",
      "Strike": 260.0,
      "Structural_Target": 346.0400000000001,
      "Premium_Mid": 7.55,
      "RR": 0.0,
      "RR_computable": 10.396
    },
    {
      "Ticker": "ZM",
      "Instrument": "LONG_CALL",
      "Strike": 92.5,
      "Structural_Target": 97.86,
      "Premium_Mid": 3.875,
      "RR": 0.0,
      "RR_computable": 0.383
    },
    {
      "Ticker": "MO",
      "Instrument": "LONG_CALL",
      "Strike": 70.0,
      "Structural_Target": 74.69999999999999,
      "Premium_Mid": 0.99,
      "RR": 0.0,
      "RR_computable": 3.747
    },
    {
      "Ticker": "BX",
      "Instrument": "LONG_CALL",
      "Strike": 130.0,
      "Structural_Target": 135.74999999999997,
      "Premium_Mid": 3.55,
      "RR": 0.0,
      "RR_computable": 0.62
    },
    {
      "Ticker": "GOOGL",
      "Instrument": "LONG_CALL",
      "Strike": 340.0,
      "Structural_Target": 369.4400000000001,
      "Premium_Mid": 9.65,
      "RR": 0.0,
      "RR_computable": 2.051
    },
    {
      "Ticker": "IGV",
      "Instrument": "DEBIT_SPREAD_CALL",
      "Strike": 95.0,
      "Structural_Target": 100.89,
      "Premium_Mid": 2.475,
      "RR": 0.0,
      "RR_computable": 1.38
    },
    {
      "Ticker": "XLE",
      "Instrument": "LONG_CALL",
      "Strike": 60.0,
      "Structural_Target": 62.54,
      "Premium_Mid": 1.205,
      "RR": 0.0,
      "RR_computable": 1.108
    },
    {
      "Ticker": "XOM",
      "Instrument": "LONG_CALL",
      "Strike": 157.5,
      "Structural_Target": 166.39,
      "Premium_Mid": 3.25,
      "RR": 0.0,
      "RR_computable": 1.735
    }
  ]
}
```

</details>

### LABQA-009 — [P0] Structural_Target on the unprofitable side of the strike

**Class:** `THESIS_CONTRACT_MISMATCH`  
**Confidence:** 95%  

29 row(s) hold a target that the contract cannot profit from — e.g. a long put with a target above the strike.

**Consequence.** Either Structural_Target is overloaded (profit target on some rows, invalidation level on others) or contract selection mismatched the thesis. Both invalidate any R:R computed from this field.

<details><summary>Evidence</summary>

```json
{
  "affected_rows": 29,
  "of_which_GO": 19,
  "by_verdict": {
    "GO": 19,
    "CONTRACT_REPAIR": 10
  },
  "examples": [
    {
      "Ticker": "AVGO",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 390.0,
      "Structural_Target": 411.12,
      "RR": 0.0,
      "Priority_Rank": 19
    },
    {
      "Ticker": "FCX",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 65.0,
      "Structural_Target": 72.25999999999999,
      "RR": 0.0,
      "Priority_Rank": 28
    },
    {
      "Ticker": "NKE",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "DEBIT_SPREAD_PUT",
      "Strike": 42.5,
      "Structural_Target": 46.38999999999999,
      "RR": 0.0,
      "Priority_Rank": 29
    },
    {
      "Ticker": "CCI",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 77.5,
      "Structural_Target": 83.97000000000001,
      "RR": 0.0,
      "Priority_Rank": 35
    },
    {
      "Ticker": "F",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 15.0,
      "Structural_Target": 16.36,
      "RR": 0.0,
      "Priority_Rank": 36
    },
    {
      "Ticker": "CME",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 275.0,
      "Structural_Target": 283.2600000000001,
      "RR": 0.0,
      "Priority_Rank": 41
    },
    {
      "Ticker": "GIS",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 37.5,
      "Structural_Target": 40.36,
      "RR": 0.0,
      "Priority_Rank": 44
    },
    {
      "Ticker": "GME",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "DEBIT_SPREAD_PUT",
      "Strike": 22.0,
      "Structural_Target": 23.2,
      "RR": 0.0,
      "Priority_Rank": 46
    },
    {
      "Ticker": "UBER",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 72.5,
      "Structural_Target": 77.85000000000002,
      "RR": 0.0,
      "Priority_Rank": 52
    },
    {
      "Ticker": "MCD",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 270.0,
      "Structural_Target": 293.84,
      "RR": 0.0,
      "Priority_Rank": 54
    },
    {
      "Ticker": "NVS",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 160.0,
      "Structural_Target": 169.24,
      "RR": 0.0,
      "Priority_Rank": 58
    },
    {
      "Ticker": "APO",
      "Verdict": "GO",
      "Direction": "PUT",
      "Instrument": "LONG_PUT",
      "Strike": 125.0,
      "Structural_Target": 132.13,
      "RR": 0.0,
      "Priority_Rank": 59
    }
  ]
}
```

</details>

### LABQA-010 — [P0] Negative EV rounds to negative zero in the export

**Class:** `SIGN_LOSS`  
**Confidence:** 95%  

4 row(s) export EV as '-0.0000'. Parsed, this equals 0.0, so a non-negative filter admits them.

**Consequence.** A filter of EV >= 0 admits genuinely negative-EV trades. A filter of EV > 0 discards rows whose true EV is positive but below the rounding threshold. Sign survives only in EV_Decision.

<details><summary>Evidence</summary>

```json
{
  "negative_zero_rows": 4,
  "exported_decimal_places": 4,
  "rows_with_EV_zero_after_parse": 19
}
```

</details>

### LABQA-004 — [P1] 1 numeric column(s) constant on every row

**Class:** `HARDCODED_DEFAULT`  
**Confidence:** 80%  

A numeric field identical across all rows usually indicates a fallback constant rather than a computed value.

**Consequence.** A scoring input that does not vary carries no information and may mask an upstream phase that did not run.

<details><summary>Evidence</summary>

```json
{
  "columns": [
    {
      "column": "Trigger_Score",
      "value": "55.0"
    }
  ],
  "row_count": 96
}
```

</details>

### LABQA-006 — [P1] Numeric column(s) with many zeros and no nulls

**Class:** `NULL_AS_ZERO`  
**Confidence:** 70%  

Zero may be encoding 'not computed'. A consumer cannot distinguish a genuine zero from a missing value.

**Consequence.** Threshold filters treat missing data as a real measurement.

<details><summary>Evidence</summary>

```json
{
  "columns": [
    {
      "column": "RR",
      "zero_pct": 45.8,
      "nulls": 0
    }
  ]
}
```

</details>

### LABQA-011 — [P1] Identical exported EV maps to different EV_Decision values

**Class:** `CLASSIFICATION_AMBIGUITY`  
**Confidence:** 90%  

Rows with EV parsing to exactly 0 carry more than one decision label — the decision retains information the number has lost.

**Consequence.** EV_Decision is the only reliable EV filter. Any consumer filtering on the numeric column is wrong.

<details><summary>Evidence</summary>

```json
{
  "rows_at_zero": 19,
  "decisions_at_zero": {
    "WEAK": 15,
    "AVOID": 4
  },
  "crosstab": {
    "neg": {
      "AVOID": 3,
      "WEAK": 0
    },
    "pos": {
      "AVOID": 0,
      "WEAK": 74
    },
    "zero": {
      "AVOID": 4,
      "WEAK": 15
    }
  }
}
```

</details>

### LABQA-012 — [P1] Priority_Rank is not ordered by Priority_Score

**Class:** `ORDERING`  
**Confidence:** 99%  

Sorting by rank and sorting by score give different candidate sets.

**Consequence.** Two plausible reading conventions produce materially different top-N selections. The rule must be documented and the consumer verified against it.

<details><summary>Evidence</summary>

```json
{
  "by_verdict": {
    "ARMED": {
      "rank_min": 2,
      "rank_max": 57,
      "score_min": 36.1,
      "score_max": 85.0,
      "n": 5
    },
    "CONTRACT_REPAIR": {
      "rank_min": 68,
      "rank_max": 96,
      "score_min": 32.6,
      "score_max": 86.8,
      "n": 29
    },
    "GO": {
      "rank_min": 1,
      "rank_max": 67,
      "score_min": 32.1,
      "score_max": 87.8,
      "n": 62
    }
  },
  "monotonic_within_verdict": true,
  "top10_by_rank": [
    {
      "Priority_Rank": 1,
      "Ticker": "T",
      "Priority_Score": 87.8
    },
    {
      "Priority_Rank": 2,
      "Ticker": "VZ",
      "Priority_Score": 85.0
    },
    {
      "Priority_Rank": 3,
      "Ticker": "PEP",
      "Priority_Score": 83.8
    },
    {
      "Priority_Rank": 4,
      "Ticker": "STZ",
      "Priority_Score": 83.6
    },
    {
      "Priority_Rank": 5,
      "Ticker": "NOW",
      "Priority_Score": 83.3
    },
    {
      "Priority_Rank": 6,
      "Ticker": "WMT",
      "Priority_Score": 82.1
    },
    {
      "Priority_Rank": 7,
      "Ticker": "CLX",
      "Priority_Score": 79.1
    },
    {
      "Priority_Rank": 8,
      "Ticker": "FXI",
      "Priority_Score": 78.9
    },
    {
      "Priority_Rank": 9,
      "Ticker": "IWM",
      "Priority_Score": 45.4
    },
    {
      "Priority_Rank": 10,
      "Ticker": "ELV",
      "Priority_Score": 45.3
    }
  ],
  "top10_by_score": [
    {
      "Priority_Rank": 1,
      "Ticker": "T",
      "Priority_Score": 87.8
    },
    {
      "Priority_Rank": 68,
      "Ticker": "TRV",
      "Priority_Score": 86.8
    },
    {
      "Priority_Rank": 69,
      "Ticker": "GM",
      "Priority_Score": 85.7
    },
    {
      "Priority_Rank": 70,
      "Ticker": "VTI",
      "Priority_Score": 85.6
    },
    {
      "Priority_Rank": 2,
      "Ticker": "VZ",
      "Priority_Score": 85.0
    },
    {
      "Priority_Rank": 71,
      "Ticker": "NEE",
      "Priority_Score": 84.1
    },
    {
      "Priority_Rank": 3,
      "Ticker": "PEP",
      "Priority_Score": 83.8
    },
    {
      "Priority_Rank": 4,
      "Ticker": "STZ",
      "Priority_Score": 83.6
    },
    {
      "Priority_Rank": 5,
      "Ticker": "NOW",
      "Priority_Score": 83.3
    },
    {
      "Priority_Rank": 72,
      "Ticker": "BMNR",
      "Priority_Score": 83.0
    }
  ]
}
```

</details>

### LABQA-014 — [P1] Vol_State and IVP_Label contradict on the same row

**Class:** `SEMANTIC_COLLISION`  
**Confidence:** 85%  

20 row(s) are Vol_State=CHEAP while IVP_Label indicates expensive. The two fields share a near-identical vocabulary in adjacent columns.

**Consequence.** If these are different concepts (realised vol regime vs implied vol percentile) the naming is unsafe. If they are the same concept, one is wrong.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "CHEAP": {
      "CHEAP": 5,
      "EXP": 0,
      "FAIR": 0
    },
    "EXPENSIVE": {
      "CHEAP": 20,
      "EXP": 28,
      "FAIR": 19
    },
    "FAIR": {
      "CHEAP": 20,
      "EXP": 0,
      "FAIR": 4
    }
  },
  "IVP_range_by_Vol_State": {
    "CHEAP": {
      "min": 29.4,
      "max": 100.0,
      "count": 45
    },
    "EXP": {
      "min": 74.1,
      "max": 100.0,
      "count": 28
    },
    "FAIR": {
      "min": 50.4,
      "max": 100.0,
      "count": 23
    }
  },
  "contradicting_rows": 20
}
```

</details>

### LABQA-015 — [P1] 'GO' selects different row counts depending on the column used

**Class:** `VOCAB_INCONSISTENCY`  
**Confidence:** 95%  

Verdict-like columns disagree on which rows are GO.

**Consequence.** The filter column choice silently changes the candidate population.

<details><summary>Evidence</summary>

```json
{
  "go_row_count_by_column": {
    "Verdict": 62,
    "Lab_Verdict": 62,
    "Exec_Category": 67,
    "Morning_Permission": 67,
    "MV_Verdict": 67
  },
  "vocabularies": {
    "Verdict": [
      "ARMED",
      "CONTRACT_REPAIR",
      "GO"
    ],
    "Lab_Verdict": [
      "ARMED",
      "CONTRACT_REPAIR",
      "GO"
    ],
    "Exec_Category": [
      "CONTRACT_REPAIR",
      "GO"
    ],
    "Morning_Permission": [
      "CONTRACT_REPAIR",
      "GO"
    ],
    "MV_Verdict": [
      "FLAG",
      "GO"
    ],
    "Campaign": [
      "ARMED",
      "CONTRACT_REPAIR",
      "READY_EXECUTE"
    ],
    "Effective_Execution_Verdict": [
      "MORNING_VALIDATION_REQUIRED",
      "STRUCTURAL_WATCH"
    ]
  }
}
```

</details>

### LABQA-016 — [P1] 'Verdict' and 'Lab_Verdict' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "ARMED": {
      "ARMED": 5,
      "CONTRACT_REPAIR": 0,
      "GO": 0
    },
    "CONTRACT_REPAIR": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "GO": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 0,
      "GO": 62
    }
  }
}
```

</details>

### LABQA-017 — [P1] 'Verdict' and 'Campaign' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "ARMED": {
      "ARMED": 5,
      "CONTRACT_REPAIR": 0,
      "GO": 0
    },
    "CONTRACT_REPAIR": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "READY_EXECUTE": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 0,
      "GO": 62
    }
  }
}
```

</details>

### LABQA-018 — [P1] 'Lab_Verdict' and 'Campaign' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "ARMED": {
      "ARMED": 5,
      "CONTRACT_REPAIR": 0,
      "GO": 0
    },
    "CONTRACT_REPAIR": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "READY_EXECUTE": {
      "ARMED": 0,
      "CONTRACT_REPAIR": 0,
      "GO": 62
    }
  }
}
```

</details>

### LABQA-019 — [P1] 'Exec_Category' and 'Morning_Permission' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "CONTRACT_REPAIR": {
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "GO": {
      "CONTRACT_REPAIR": 0,
      "GO": 67
    }
  }
}
```

</details>

### LABQA-020 — [P1] 'Exec_Category' and 'MV_Verdict' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "FLAG": {
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "GO": {
      "CONTRACT_REPAIR": 0,
      "GO": 67
    }
  }
}
```

</details>

### LABQA-021 — [P1] 'Morning_Permission' and 'MV_Verdict' are perfectly collinear

**Class:** `FALSE_INDEPENDENCE`  
**Confidence:** 85%  

One is a relabelling of the other, not an independent assessment.

**Consequence.** If one of these is treated as independent confirmation of the other, it provides none.

<details><summary>Evidence</summary>

```json
{
  "crosstab": {
    "FLAG": {
      "CONTRACT_REPAIR": 29,
      "GO": 0
    },
    "GO": {
      "CONTRACT_REPAIR": 0,
      "GO": 67
    }
  }
}
```

</details>

### LABQA-023 — [P1] Candidate population varies with filter choice

**Class:** `FILTER_SENSITIVITY`  
**Confidence:** 95%  

Population ranges 22–67 across plausible filter definitions.

**Consequence.** The rank-1 candidate is stable across variants while the population beneath it is not — which is why a filter defect can stay invisible.

<details><summary>Evidence</summary>

```json
{
  "variants": {
    "Verdict=='GO'": {
      "n": 62,
      "top_by_rank": [
        "T"
      ]
    },
    "Exec_Category=='GO'": {
      "n": 67,
      "top_by_rank": [
        "T"
      ]
    },
    "Verdict in GO/GO_LIMIT/PROBE/ARMED": {
      "n": 67,
      "top_by_rank": [
        "T"
      ]
    },
    "GO & RR>0": {
      "n": 30,
      "top_by_rank": [
        "T"
      ]
    },
    "GO & EV>0": {
      "n": 50,
      "top_by_rank": [
        "T"
      ]
    },
    "GO & EV>=0": {
      "n": 62,
      "top_by_rank": [
        "T"
      ]
    },
    "GO & RR>0 & EV>0": {
      "n": 22,
      "top_by_rank": [
        "T"
      ]
    }
  },
  "spread_ratio": 3.05,
  "distinct_top_candidates": 1
}
```

</details>

### LABQA-003 — [P2] 2 column(s) >=75% null

**Class:** `SPARSE_COLUMN`  
**Confidence:** 95%  

Sparse but not empty.

<details><summary>Evidence</summary>

```json
{
  "columns": [
    {
      "column": "WBS_Grade",
      "null_pct": 81.2
    },
    {
      "column": "WBS_Score",
      "null_pct": 81.2
    }
  ]
}
```

</details>

### LABQA-005 — [INFO] Constant columns (all rows identical)

**Class:** `CONSTANT`  
**Confidence:** 99%  

Review whether each is legitimately per-run.

<details><summary>Evidence</summary>

```json
{
  "columns": [
    {
      "column": "Options_Research_Permission",
      "value": "MANUAL_REVIEW_REQUIRED"
    },
    {
      "column": "Trigger_Display",
      "value": "-"
    },
    {
      "column": "Trigger_Evidence",
      "value": "TRIGGER 55"
    },
    {
      "column": "Trigger_Score",
      "value": "55.0"
    },
    {
      "column": "Win_Rate_Source",
      "value": "ACTUARIAL"
    }
  ]
}
```

</details>

### LABQA-007 — [INFO] R:R formula reconciliation

**Class:** `FORMULA`  
**Confidence:** 95%  

RR = clip((intrinsic_at_target - premium_mid) / premium_mid, 0), direction-aware.

<details><summary>Evidence</summary>

```json
{
  "rows_checked": 96,
  "rows_matching": 83,
  "match_pct": 86.5
}
```

</details>

### LABQA-013 — [INFO] IVP_Label is a clean function of IVP

**Class:** `LABEL`  
**Confidence:** 95%  

Thresholds inferred from data.

<details><summary>Evidence</summary>

```json
{
  "ranges": {
    "CHEAP": {
      "min": 29.4,
      "max": 38.7,
      "count": 5
    },
    "EXPENSIVE": {
      "min": 65.2,
      "max": 100.0,
      "count": 67
    },
    "FAIR": {
      "min": 42.4,
      "max": 64.9,
      "count": 24
    }
  }
}
```

</details>

### LABQA-022 — [INFO] Contract field sanity

**Class:** `CONTRACT_SANITY`  
**Confidence:** 90%  

Basic validity of strike/premium/DTE/expiry.

<details><summary>Evidence</summary>

```json
{
  "expiry_distinct_values": 4,
  "expiry_span_days": 21
}
```

</details>

### LABQA-024 — [INFO] Run_ID present in content and filename

**Class:** `IDENTITY`  
**Confidence:** 99%  

Run binding can be enforced from file content.

<details><summary>Evidence</summary>

```json
{
  "run_id": "20260731_083130"
}
```

</details>

---

## What this audit does not establish

- **Cause.** Every finding is a property of the exported data. Whether it originates upstream, in the Lab merge, or at export requires source review.
- **Whether findings are systemic.** Run across several exports from different dates to separate systemic defects from artefacts of one run.
- **Field intent.** Where a field's meaning is undefined, no test can decide whether it is wrong.