# RFI Contradiction-Checker — methodology (v1.0.0)

How Okojo decomposes a subject's Request-For-Information response into discrete
claims, tests each one against the evidence, and decides what that evidence
supports. Companion to `scoring-methodology.md`, `advisory-methodology.md`, and
`sar-critic-methodology.md`.

This is a **synthetic-data research prototype**. It *surfaces* and *proposes*;
a human investigator reviews, decides, and files. Nothing here is a
determination.

---

## 1. Why this capability exists

A polished RFI narrative is the hardest thing in an investigation to falsify by
reading. The assertions are individually plausible, legalistic, and spread
across systems no single reviewer holds in their head at once — a licensed-trust
"segregation" claim is refuted by device data, an "unrelated counterparty"
claim by a corporate registry, a "lawful trade settlement" claim by the ledger.
Catching that today depends on one analyst happening to remember the right
record. This makes it systematic: every claim is tested against every evidence
surface, and every rebuttal carries a pointer to the row behind it.

## 2. Pipeline

```
RFI response text
  -> split into assertion-level sentences
  -> align each stored claim to its sentence (RapidFuzz)      [decomposition]
  -> run four adversarial probes over the evidence            [checkers]
  -> weigh the rebuttals under a corroboration gate           [adjudication]
  -> claim-by-claim contradiction table, with citations
```

Every stage is deterministic and runs with **no LLM**. Same inputs, same table.

## 3. Decomposition

Sentences split on terminal punctuation; each stored claim is aligned to the
sentence it came from by RapidFuzz `token_set_ratio`, which tolerates the
reordering and elision between a narrative sentence and its canonical claim
form. The alignment score is retained so the pairing is auditable.

A claim aligning below the floor is **still emitted**, flagged as weakly
aligned; a sentence no claim matched is **reported, not discarded**. Silent
dropping would hide exactly the assertion someone wanted hidden.

Only the RFI *under review* is decomposed. A prior RFI is evidence, never a
subject of adjudication.

## 4. The four probes

Each probe first asks *"is this the kind of assertion I can test?"* using a
published lexicon, then looks for rebutting rows. **Applicability is derived
from the claim's text, never from its identity** — wiring a probe to a claim id
would tell the system which claims to attack, and the evaluation would be
measuring its own answer key.

| Probe | Applies when the claim… | Rebuts with |
|---|---|---|
| `registry` | denies a relationship with a named entity | officer appointments shared across both companies over **overlapping** windows |
| `prior_rfi` | denies a relationship with a named entity | the subject's own earlier answer naming that entity in an affirming relationship phrase |
| `onchain` | denies a relationship, **or** asserts a source of funds | direct transfers between the two parties; a value path to a synthetic-sanctioned address; structured round-number transfers; gas-funded hops |
| `device` | asserts exclusive control or segregation | a `device_fingerprint` shared with other accounts |

Named entities resolve through the shared `EntityBackbone`, so "the claim names
this counterparty" means the same thing here as in the screener and tell miner.

**Scope boundary (deliberate).** The on-chain probe tests fund-flow assertions
and counterparty-relationship denials. It does **not** argue about custody or
segregation claims — control commingling is the device probe's job. Extending
on-chain to reason about custody from gas-funding is a defensible future probe;
it would be a scope change, and would need its own re-baselined evaluation.

## 5. Adjudication — four verdicts, one flag

| Verdict | Meaning |
|---|---|
| `contradicted` | the evidence rebuts the claim — **the only flag** |
| `qualified` | evidence cuts against part of the claim without refuting it |
| `uncontested` | a probe could test the claim and found nothing against it |
| `unverifiable` | no probe can test it; the evidence is silent either way |

The **corroboration gate** mirrors the advisory matcher's: a claim reaches
`contradicted` only on one rebuttal at or above the strong bar, **or** on
corroboration across at least two independent evidence surfaces. A lone weak
signal yields `qualified`.

Keeping `qualified` and `unverifiable` distinct from `contradicted` is a
precision control, not bookkeeping. A claim that is true as far as it goes but
omits material control is not a lie; calling it one would be an over-claim of
exactly the kind this project's calibrated-language rule forbids. And silence
because nothing can test an assertion is not the same as silence because the
evidence agrees — collapsing them would let the checker take credit for
questions it never asked.

**Confidence** is a noisy-OR over rebuttal strengths,
`1 - prod(1 - strength_i)`: independent evidence accumulates, and no finite
amount of weak evidence reaches certainty. It expresses how much evidence is
stacked against a claim — it is **not** a probability that the subject lied.

## 6. Grounding

Every rebuttal carries the provenance of the rows supporting it, and a
contradiction reaching the SAR draft cites **both** the RFI row and the
rebutting evidence row. Those claims pass the same two-stage, fail-closed
grounding contract as every other SAR claim: no claim without a pointer, and no
pointer to a row that does not exist.

## 7. What the checker may not see

The scenario's answer key — per-claim verdicts, declared rebuttal sources, and
the helper uid lists in `ground_truth.json` — exists for the evaluation only.
The decomposer and the probes read evidence tables exclusively; tests assert
their source never even names those keys. Otherwise the evaluation would be
scoring the system against data the system was handed.

## 8. Canonical parameters

These are **tunable policy parameters**, not constants of nature. They are
versioned, stamped into the tamper-evident audit trail on every run, and
regression-tested against this document, so code and doc cannot drift.

<!-- rfi-contradiction-config:begin -->
```json
{
  "version": "1.0.0",
  "strong_rebuttal": 0.8,
  "min_corroborating_sources": 2,
  "sources": [
    "device",
    "onchain",
    "prior_rfi",
    "registry"
  ],
  "verdicts": [
    "contradicted",
    "qualified",
    "uncontested",
    "unverifiable"
  ],
  "weights": {
    "registry_common_officer": 0.8,
    "prior_rfi_self_contradiction": 0.8,
    "onchain_sanctioned_exposure": 0.9,
    "onchain_gas_funded_hop": 0.6,
    "onchain_structured": 0.5,
    "onchain_counterparty_flow": 0.5,
    "device_shared_fingerprint": 0.5
  },
  "lexicon_sizes": {
    "relationship_denial": 8,
    "source_of_funds": 7,
    "exclusive_control": 6,
    "relationship_affirmation": 7
  }
}
```
<!-- rfi-contradiction-config:end -->

### Why each weight is what it is

| Parameter | Value | Rationale |
|---|---|---|
| `onchain_sanctioned_exposure` | 0.9 | A traced value path to a sanctioned endpoint is the strongest single item available — it is a ledger fact, not an inference. |
| `registry_common_officer` | 0.8 | A shared director over overlapping windows is documentary and hard to explain away, but registries lag reality, so not 0.9. |
| `prior_rfi_self_contradiction` | 0.8 | The subject's own words are strong evidence; the discount reflects that circumstances legitimately change between answers. |
| `onchain_gas_funded_hop` | 0.6 | Gas funding strongly suggests control, but a third party can pay gas for benign reasons. |
| `onchain_structured` | 0.5 | Structuring is suggestive, never dispositive on its own. |
| `onchain_counterparty_flow` | 0.5 | Transfers prove contact, not ownership — genuine arm's-length parties also transact. |
| `device_shared_fingerprint` | 0.5 | A shared device evidences commingled control, but shared offices and hardware exist. |
| `strong_rebuttal` | 0.8 | Set so that documentary evidence stands alone while behavioural signals must corroborate. |
| `min_corroborating_sources` | 2 | Two *independent surfaces* — not two findings from one probe — so a single noisy source cannot self-corroborate. |

Weights are seeded from investigative judgement rather than fitted to the
scenario; they are policy inputs a compliance function would own, and any change
bumps the version and re-runs the evaluation.

## 9. Evaluation

Scored against `data/synthetic/ground_truth.json`'s `rfi_claim_key`, which
grades **all four** claims so every verdict branch has a gold value:

- **Detection P/R/F1** — the positive class is strictly *adjudicated
  `contradicted`*. `qualified` and `unverifiable` are correct non-positive
  outcomes; a false positive is a claim escalated all the way to `contradicted`.
- **Verdict and rebuttal-source discrimination** — per claim, the verdict and
  the exact set of probes that fired must match the key.

## 10. Limitations

- The lexicons are English and hand-authored; a paraphrase outside them makes a
  claim look untestable. `unverifiable` is a real outcome, not a failure — but
  it is also where a determined narrative would aim.
- Confidence measures evidence weight, not truth.
- Weights are unfitted judgement calls, deliberately: fitting them to a
  synthetic scenario would manufacture accuracy that would not transfer.
- The checker proposes; it never concludes. Every verdict is for human review.
