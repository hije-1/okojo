# SAR Drafter + Critic Methodology (v1.0.0)

**Status:** synthetic-data research prototype. Not production screening, not legal
or compliance advice, not a SAR-filing tool. Okojo *drafts* a narrative and
*grades* it against an operationalized rubric; a human investigator reviews,
decides, and files. This document explains *how* the drafter stays grounded, *how*
the Critic grades a draft, and *why* each parameter has the value it does. It is
written for an investigator, a model-risk reviewer, and an external auditor alike.

Three principles govern everything below:

1. **No receipt, no claim.** Every asserted fact traces to a specific evidence row
   via a provenance pointer, and the pointer must *resolve* to a row that actually
   exists. A claim that is uncitable — or that cites a row not in the evidence — is
   rejected fail-closed, not softened.
2. **The Critic surfaces gaps; it never fabricates.** Revision only re-assembles
   grounded claims from evidence already retrieved. Any rubric element the evidence
   cannot support is left uncovered and **flagged for human review** — surfaced,
   never invented.
3. **Deterministic and bounded is a compliance feature.** No LLM, no randomness:
   the same inputs produce the same draft, the same grade, and the same number of
   revision passes. The revision loop is hard-capped and reaches a fixpoint well
   inside the cap, so it can never spin.

---

## 1. The grounding contract (two fail-closed checks)

A draft is a list of typed **claims**, each carrying one or more provenance
pointers. Two independent checks run before any draft is accepted:

- **Grounded** — every claim carries at least one provenance pointer. A claim with
  none is rejected (`UngroundedClaimError`).
- **Resolvable** — every pointer's `(source, row_key)` names an actual row in the
  mock evidence stores. A well-formed pointer to a row that does not exist is
  rejected (`UnresolvableCitationError`). The optional `.field` sub-pointer names a
  *column within* the row, so resolution ignores it: if the row exists, the column
  citation is grounded in it.

Resolution is a membership test over every evidence table a claim can cite
(accounts, KYC, devices, IP logs, addresses, transactions, gas-funding, RFI,
sanctions watchlist), built by reusing the connectors' own provenance
construction — so a claim built from a real record always resolves, and a
fabricated pointer never does. The grounding report (total / grounded / resolved /
unresolved) is stamped into the tamper-evident audit trail
(`sar_drafter / grounding_validated`).

---

## 2. The FinCEN narrative rubric

FinCEN expects a SAR narrative to answer *who / what / when / where / why / how*,
identify the **predicate offense**, characterize the **subject and network**, and
— for a crypto matter — marshal **on-chain evidence**. Okojo operationalizes that
expectation as a fixed rubric. Each element maps to the claim types whose presence
satisfies it (any one suffices):

| Element | Satisfied by | Rationale |
|---|---|---|
| **who** | subject-identity claim | The narrative must name the subject. |
| **what** | surfaced anomaly claim(s) | The suspicious activity itself. |
| **when** | activity-timeframe claim | The window the timeline spans (first..last event). |
| **where** | jurisdiction/geography claim | Declared residence vs. observed login geographies. |
| **why** | predicate-offense **or** matched advisory | The regulatory basis: sanctioned on-chain exposure and/or a FinCEN advisory typology. |
| **how** | mechanism claim | The concrete methodology: structured transfers, gas-funding linkage, reused KYC. |
| **subject_and_network** | network expansion **or** attribution tell | How the subject connects to the wider cluster. |
| **on_chain_evidence** | network sanctioned-exposure **or** explicit on-chain claim | The blockchain evidence a crypto SAR is expected to marshal. |

**Coverage** is the weighted fraction of rubric elements a draft satisfies. Weights
are equal (1.0) pending calibration — a deploying institution would weight the
elements against its own examiner feedback. A draft **clears the Critic** iff every
required element is present and coverage meets the threshold.

### Why the threshold is 1.0
For this prototype, a draft clears without human-review escalation only when it
covers **every** rubric element. Anything less is escalated: the uncovered
element(s) are named in the filing note and flagged for an analyst. This is a
deliberately conservative, fail-closed stance — the Critic would rather escalate a
partially-evidenced draft to a human than pass it. The threshold is a tunable
*policy parameter*: an institution comfortable filing on a subset (e.g. the five
core W/H elements) would lower it and mark the crypto-specific elements optional.

---

## 3. The bounded revision loop

1. The drafter builds a grounded first draft and the Critic grades it.
2. While the draft is below the bar **and** the cap is not reached: the loop asks
   the drafter to fill the Critic's gap list from evidence already in hand
   (a timeframe from the timeline, geography from residence + IP logs, a predicate
   from sanctioned exposure and/or the advisory, mechanisms from structured
   transfers / gas-funding / reused KYC). Each revised draft re-passes the full
   grounding contract, fail-closed.
3. The loop stops at a **fixpoint** — the instant a pass adds no new grounded claim
   — or at the hard cap, whichever comes first.
4. Any element still uncovered is written into the filing note as a **human-review
   flag** (`sar_critic / human_fallback`), never fabricated.

Every step is stamped into the audit trail: the versioned config, the first-pass
grade, one record per revision pass (which elements it addressed), and a terminal
`converged` or `human_fallback` record. The chain re-verifies end-to-end.

### Measured value (ablation)
On the synthetic scenario, the loop raises covered-rubric-element recall against
the gold key from **0.56 (template-first draft) to 1.00 (with the Critic loop)**,
while never over-claiming (precision stays 1.0 in both). See
`tests/test_sar_eval.py`.

---

## 4. Calibrated language

All drafted and revised claims use calibrated verbs — *proposes / surfaces /
drafts / flags* — and never *instantly*, *autonomously*, *guaranteed*, *proven
fact*, *definitely*, or *certainly*. The predicate claim is explicitly framed as
"proposed for analyst assessment, not a determination." A calibration check runs
over every draft.

---

## 5. Versioned, reproducible configuration

Every run stamps its Critic configuration into the tamper-evident audit trail
(`sar_critic / critic_config`), so any historical grade can be reproduced exactly
from the record. The canonical parameter set for this version is below; it is the
single source of truth (`okojo.sar.critic_config`) and is regression-tested against
this document, so the doc and the code can never silently drift.

**Version 1.0.0 — canonical parameters:**

<!-- sar-critic-config:begin -->
```json
{
  "version": "1.0.0",
  "threshold": 1.0,
  "elements": [
    {"key": "who", "weight": 1.0, "required": true},
    {"key": "what", "weight": 1.0, "required": true},
    {"key": "when", "weight": 1.0, "required": true},
    {"key": "where", "weight": 1.0, "required": true},
    {"key": "why", "weight": 1.0, "required": true},
    {"key": "how", "weight": 1.0, "required": true},
    {"key": "subject_and_network", "weight": 1.0, "required": true},
    {"key": "on_chain_evidence", "weight": 1.0, "required": true}
  ]
}
```
<!-- sar-critic-config:end -->

Bump `version` whenever the rubric, a weight, or the threshold changes;
already-audited grades remain reproducible under the version they were computed
with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public (OFAC
SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
