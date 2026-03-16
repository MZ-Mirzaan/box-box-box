# Phase 1 — Data Exploration Notes

**Date**: 2026-03-16

## Dataset Profile

| Property | Value |
|---|---|
| Total races available | 30,000 (30 files × 1000) |
| Races analyzed | 5,000 |
| Tracks | 7 (Suzuka, Monza, Silverstone, COTA, Monaco, Spa, Bahrain) |
| Total laps range | 25 – 70 (avg 45.4) |
| Base lap time range | 80.0 – 95.0s (avg 87.6) |
| Pit lane time range | 20.0 – 24.0s (avg 22.0) |
| Track temp range | 18 – 42°C (avg 30.4) |

## Strategy Patterns

- **91.5% of drivers use 1-stop** strategies, only 8.5% use 2-stop
- Starting compound roughly even: MEDIUM 33.6%, HARD 34.1%, SOFT 32.4%
- HARD is the most-used compound overall (stint-length bias)

### Typical Stint Lengths

| Compound | Min | Max | Avg |
|---|---|---|---|
| SOFT | 5 | 52 | 15.1 |
| MEDIUM | 5 | 62 | 21.3 |
| HARD | 7 | 62 | 27.9 |

## Pairwise Compound Analysis

Head-to-head among 1-stop drivers by starting compound:

| Matchup | Result |
|---|---|
| HARD vs MEDIUM | MEDIUM wins 51.3% |
| HARD vs SOFT | Nearly 50/50 (50.0% each) |
| MEDIUM vs SOFT | SOFT wins 56.1% |

**Insight**: SOFT wins more often when starting compound differs — but it's not overwhelming. This confirms compound offsets interact with stint length and temperature, not just raw speed.

## Grid Search Results (Linear Degradation)

Best parameters found via coarse + fine grid search on 1000 races:

| Parameter | Value |
|---|---|
| SOFT offset | -1.1 s/lap (faster) |
| MEDIUM offset | 0.0 (reference) |
| HARD offset | +0.65 s/lap (slower) |
| SOFT deg rate | 0.07 s/lap/age |
| MEDIUM deg rate | 0.005 s/lap/age |
| HARD deg rate | 0.005 s/lap/age |

### Accuracy

| Test Set | Accuracy |
|---|---|
| 1000 training races | 7.5% |
| 5000 historical races | 6.6% |
| 100 test cases | 4/100 (4%) |

## What Didn't Work

- **Quadratic degradation** (age²): 3.8% — worse than linear
- **Simple temperature multiplier** `(1 + coeff × (temp - 30))`: no improvement at all

## Key Takeaways

1. **The formula is more complex than `offset + rate × age`** — 7.5% accuracy proves the structure is wrong, not just the parameters
2. **Temperature does matter** (winner profiles shift at extreme temps) but interacts in a non-trivial way — possibly per-compound temperature sensitivity
3. The regulations mention an **"initial performance period"** before degradation kicks in — this threshold/cliff behavior may be the missing piece
4. **SOFT degrades ~14x faster than HARD** — the right ballpark, but the functional form needs work

## What to Try in Phase 2

- [ ] Degradation with a **threshold** (N laps of constant performance, then linear/quadratic ramp)
- [ ] **Per-compound temperature coefficients** instead of a single multiplier
- [ ] **scipy.optimize** with continuous parameter space instead of grid search
- [ ] Fit against **all 30k races** for robust convergence
- [ ] Consider **fuel effect** or other hidden variables
