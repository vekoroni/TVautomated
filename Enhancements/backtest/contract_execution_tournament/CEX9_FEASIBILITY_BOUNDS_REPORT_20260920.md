# CEX-9 Contract-Family Feasibility Bounds — 2026-09-20

**State:** hindsight diagnostic only; no production authority

| Band | Families | Oracle ask→bid | Oracle spread+50 | Random median |
|---|---:|---:|---:|---:|
| H1|Q1 | 52 | -14.4% | -20.1% | -20.7% |
| H1|Q2 | 103 | -15.2% | -20.1% | -22.0% |
| H1|Q5 | 254 | -5.1% | -9.9% | -12.9% |
| H1|Q10 | 506 | -6.7% | -11.7% | -14.2% |
| H1|Q20 | 1010 | -9.7% | -15.5% | -16.9% |
| H3|Q1 | 30 | -33.1% | -40.3% | -39.4% |
| H3|Q2 | 57 | -30.6% | -37.7% | -39.5% |
| H3|Q5 | 139 | -21.8% | -28.3% | -30.2% |
| H3|Q10 | 277 | -21.8% | -28.6% | -30.6% |
| H3|Q20 | 553 | -19.1% | -25.6% | -27.7% |
| H5|Q1 | 8 | -20.2% | -27.7% | -28.8% |
| H5|Q2 | 16 | -41.3% | -46.3% | -48.1% |
| H5|Q5 | 39 | -24.5% | -33.2% | -31.2% |
| H5|Q10 | 78 | -24.3% | -31.4% | -30.9% |
| H5|Q20 | 155 | -21.8% | -28.5% | -28.1% |

## Contract + exit-horizon oracle across days 1/3/5

| Band | n | Oracle ask→bid | Oracle spread+50 | Hit ≥25% |
|---|---:|---:|---:|---:|
| Q1 | 52 | 9.9% | 1.7% | 25.0% |
| Q2 | 103 | 2.8% | -3.8% | 19.4% |
| Q5 | 254 | 10.9% | 4.6% | 25.2% |
| Q10 | 506 | 7.4% | 0.9% | 24.9% |
| Q20 | 1010 | 4.3% | -2.8% | 22.7% |

The oracle is intentionally impossible: it selects contracts and/or exit horizons using future realised return. A positive oracle proves only that the family contains learnable upside; it does not validate any selector.
