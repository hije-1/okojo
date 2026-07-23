# Scoring Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains *how* Okojo
turns evidence into the two numbers a reviewer sees, and *why* each constant has
the value it does. It is written for an investigator, a model-risk reviewer, and
an external auditor alike.

Two principles govern everything below:

1. **The cited factors are the artifact; the number is a transparent aggregation
   of them.** Every score decomposes into named factors with an explicit formula.
   A reviewer should never have to trust an opaque number — they can re-derive it.
2. **These constants are tunable *policy parameters*, not universal truths.** The
   values here are defensible defaults for the synthetic scenario; a deploying
   institution would calibrate them against its own risk appetite and back-testing.
   They are version-stamped (see below) so any historical score is reproducible.

Okojo produces two independent scores. They answer different questions and are on
different scales — they are deliberately **never** combined into one number.

---

## 1. On-chain sanctioned-exposure score (0–1)

**Question:** *How exposed is this account to the synthetic sanctioned set, by how
much tainted value flows onward and how close the account sits to the endpoint?*

The scorer operates on the already-built network graph; it never re-expands. For
each account it computes:

```
score = min(1, amount_factor × proximity_factor)
```

### 1.1 Membership — who is eligible for a money-flow score
Exposure is computed over **`{transaction, controls}` edges only**. An account is
"exposed" iff its funds have a directed path to a synthetic sanctioned endpoint
over value/control edges. This deliberately mirrors the evaluation answer key's
flow semantics, so the predicted exposed set matches the ground truth exactly
(precision/recall are structural, not tuned).

- **Why exclude gas-funding and relationship edges from membership?** A shared
  device or a gas payment is a strong *attribution* signal, but it is not a
  *money-flow*. Letting it create an "exposure" would manufacture a fund-flow
  claim the evidence does not support. Gas funding is surfaced separately (§1.5)
  so it is never lost — only kept out of the fund-flow metric.

### 1.2 Proximity factor — hop decay (`decay = 0.6`)
`proximity_factor = decay ** (hops − 1)`, where `hops` is the minimum number of
value/control edges to the nearest sanctioned endpoint. A direct counterparty
(`hops = 1`) scores `1.0`; each additional hop multiplies by `0.6`.

- **Why `0.6`?** Exposure attenuates with distance — value passing through more
  intermediaries is more diluted and more plausibly legitimate — but it should
  not vanish. `0.6` keeps a 3-hop link (`0.36`) clearly material while a direct
  hit (`1.0`) dominates. Lower values punish distance harder; higher values
  flatten the graded signal. This is the primary tuning dial for how far
  "contamination" is treated as reaching.

### 1.3 Amount factor — fixed log scale (`floor = 0.1`, `amount_ref_usdt = 1,000,000`)
`amount_factor = floor + (1 − floor) × min(1, log10(1 + tainted) / log10(1 + amount_ref))`,
where `tainted` is the USDT this account's own wallets push onward toward the
tainted path.

- **Why logarithmic, not linear?** Illicit flows span many orders of magnitude;
  a linear scale would let one whale dwarf everything. A log scale compresses the
  range so a \$10k and a \$500k mover are both meaningfully non-zero and ordered.
- **Why a fixed scale, not min–max over the cluster?** Min–max would make scores
  depend on the largest account in the current view — the same account would
  score differently in different cases. A fixed reference makes a score mean the
  same thing everywhere (reproducibility).
- **Why `floor = 0.1`?** It guarantees every flow-reachable account scores `> 0`
  even with no measured tainted amount (e.g. reachable purely via `controls`), so
  "score > 0" is exactly "reachable". It is the smallest non-trivial signal.
- **Why `amount_ref = $1,000,000`?** The amount at which the factor saturates to
  `1.0`. It sets "what counts as a large tainted flow" for this synthetic
  scenario; an institution would set it from its own transaction distribution.

### 1.4 Bands (`band_high = 0.60`, `band_medium = 0.30`)
`high ≥ 0.60`, `medium 0.30–0.60`, `low < 0.30`. Bands are a **triage aid for
human review**, not a determination. In calibrated terms the scorer *surfaces*
and *grades* exposure; a person decides and files.

### 1.5 Gas-only echo (`gas_base = 0.5`)
A gas-funding controller with no money-flow path is surfaced as a separate,
flagged row scored `gas_base × proximity_factor` and **kept out of the exposure
metric** (`exposure_path = false`). Gas funding repeatedly unmasks the controller
behind a "non-custodial" wallet, so it is never dropped — but it is an attribution
tell, not a fund-flow, so it is reported without inflating the fund-flow number.
`0.5` mirrors the graph's gas-control weight: a strong signal, below a direct
money-flow hit.

### 1.6 Worked example
An account that is a direct counterparty (`hops = 1`, so `proximity = 1.0`) moving
a saturating tainted amount (`amount_factor = 1.0`) scores
`min(1, 1.0 × 1.0) = 1.000`. Two hops back at the same amount scores
`min(1, 1.0 × 0.6) = 0.600`. This exact arithmetic is exposed per-account in the
UI ("show the math") and carried as a `ScoreDecomposition` on every score.

---

## 2. Watchlist name-similarity score (0–100)

**Question:** *Does an account's registered name resemble a sanctioned/watchlist
alias closely enough to warrant human review — despite exact-match evasion?*

- **Algorithm:** RapidFuzz `WRatio` (a weighted blend of ratio strategies robust
  to token order and length), returning `0–100`.
- **Threshold:** a match at **`≥ 85`** is surfaced for review. On the synthetic
  data, transliteration variants score ~90+ while unrelated decoys sit well below,
  so `85` cleanly separates true resemblance from noise. Lowering it admits noise;
  raising it risks missing a transliteration.
- **What the number means — read this carefully.** The score is a **name-similarity
  confidence for human review, *not* a confirmed identity match and *not* a risk
  score.** A "92" means the two strings are 92/100 similar (e.g. `Hill` vs `Holl`
  differs by one character), which is a reason to *look*, nothing more. Every hit
  is grounded in both the watchlist row and the account row; a human adjudicates.

This score is intentionally **not** on the 0–1 exposure scale and is never mixed
with it. One measures fund-flow proximity; the other measures string resemblance.

---

## 3. Reproducibility & versioning

Every scoring run stamps its configuration into the tamper-evident audit trail
(`risk_scorer / scoring_config`), so any historical score can be reproduced
exactly from the record. The canonical parameter set for this version is below;
it is the single source of truth (`okojo.scorer.scoring_config`) and is
regression-tested against this document, so the doc and the code can never
silently drift.

**Version 1.0.0 — canonical parameters:**

<!-- scoring-config:begin -->
```json
{
  "version": "1.0.0",
  "membership_edge_types": ["controls", "transaction"],
  "decay": 0.6,
  "floor": 0.1,
  "amount_ref_usdt": 1000000.0,
  "gas_base": 0.5,
  "band_high": 0.6,
  "band_medium": 0.3
}
```
<!-- scoring-config:end -->

Bump `version` whenever any parameter or the formula changes; already-audited
scores remain reproducible under the version they were computed with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
