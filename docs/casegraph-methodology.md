# Case-Graph Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains Okojo's
persistent case graph — what it records across cases, how recidivism is
surfaced at case open, and why the store is built to be reproducible — for an
investigator, a model-risk reviewer, and an external auditor alike.

Three principles govern everything below:

1. **Cross-case memory is the fix for a documented failure mode.** In
   published investigations, accounts have cleared multiple prior
   "retain and monitor" reviews before anyone connected them to a wider
   network — each review looked at the subject in isolation. The case graph
   makes the isolation impossible: every case records the entities it touched
   (devices, KYC documents, addresses, counterparty accounts), and every new
   case opens by asking what is already on record.
2. **Surfaced, never determined.** A recidivism flag is a *reason for a human
   to look*, carried with its evidence (the account's review-history fields
   and any cross-case overlaps). It never closes, blocks, escalates, or
   exempts anything — in either direction: prior *cleared* reviews do not
   clear a subject.
3. **The thresholds are tunable policy parameters, not universal truths**,
   version-stamped (see §4) so any historical flag is reproducible.

---

## 1. What a case records

At the end of every run the case is upserted into a file-backed store
(stdlib sqlite3 — read-write case *history*, kept deliberately separate from
the read-only evidence connectors):

- **`cases`** — one row per case: subject, disposition (the SAR-bar outcome
  or `insufficient_evidence`), the full bounded-decision trace as JSON, and
  the audit chain's tip hash + record count at packaging time, so the row is
  pinned to a specific tamper-evident log state.
- **`case_entities`** — the case's entity surfaces, one row per
  `(kind, key)`: the subject's `device` fingerprints, `kyc_doc`, controlled
  `address`es, and every `counterparty_account` the network expansion
  reached.

**Idempotency:** `case_id` derives from the subject (`case_<uid>`); re-running
a case replaces its rows in one transaction. Repeated demo reruns can never
duplicate history.

**Reproducibility:** no timestamps exist anywhere in the schema; every insert
comes from an explicitly sorted list and every read carries `ORDER BY`.
Recording the same sequence of cases into two fresh stores yields identical
dumps — regression-tested.

## 2. Case open — the recidivism check

Opening a case asks the store two questions and stamps the answer into the
audit chain (`case_graph / recidivism_flagged` or `case_graph /
history_clear`, with the account row as provenance):

1. **Does the subject's own review history say "seen before"?**
   `is_recidivist = prior_review_count >= 3 OR account_status in
   {retain_monitor}`. This leg works even on a cold store — the exchange's
   review history predates Okojo.
2. **Has any of this subject's entities appeared in another case?** Every
   `(kind, key)` of the subject is checked against other cases' entity rows,
   and other cases that named this subject as a counterparty are returned as
   overlaps. This leg is what turns isolated reviews into a network view, and
   it grows as more cases are run.

### Why `recidivism_prior_reviews = 3`

- **Strictly above background noise.** Ordinary synthetic accounts carry a
  planted `prior_review_count` of 0–1 — one prior look is routine, not a
  pattern. A threshold of 3 can never fire on that background.
- **"Multiple cleared reviews" is the documented pattern.** The failure mode
  is not *a* prior review; it is a subject repeatedly reviewed and repeatedly
  retained. Three is the smallest count that reads as a pattern rather than a
  coincidence.
- **Conservative of the planted case with margin.** The scenario's recidivist
  carries `prior_review_count = 5` — the "cleared five prior reviews"
  failure mode — so the flag fires with headroom rather than by exact match,
  and would still fire if the plant were varied.

### Why `retain_monitor` alone also triggers

The status *is* a prior-review disposition: an account only carries
`retain_monitor` because a previous review chose to keep it open under watch.
Treating it as a recidivism signal regardless of the count means a subject
cannot slip through on a technicality (e.g. a review history the count field
under-reports).

## 3. What the flag does — and does not — do

The recidivism view (`prior_review_count`, `account_status`, prior case ids,
entity overlaps) is: stamped into the audit chain at case open, carried on
the case result for the UI, and included in the decision-ready case package.
It feeds **no score, no decision rule, and no SAR claim** in this version —
the bounded decision points act on case evidence, not on history, so a
subject's past cannot mechanically pre-judge the present case in either
direction. Surfacing plus a human is the design, not a limitation.

## 4. Reproducibility & versioning

Every run stamps the versioned case-graph policy into the audit trail
(`case_graph / casegraph_config`), mirroring the scoring, retrieval, critic,
contradiction, and agency config stamps. The canonical policy for this
version is below; it is the single source of truth
(`okojo.casegraph.casegraph_config`) and is regression-tested against this
document, so the doc and the code can never silently drift.

**Version 1.0.0 — canonical policy:**

<!-- casegraph-config:begin -->
```json
{
  "version": "1.0.0",
  "recidivism_prior_reviews": 3,
  "recidivism_statuses": [
    "retain_monitor"
  ],
  "entity_kinds": [
    "address",
    "counterparty_account",
    "device",
    "kyc_doc"
  ],
  "store": "sqlite3 file; idempotent per-case upsert; no timestamps"
}
```
<!-- casegraph-config:end -->

Bump `version` whenever the recidivism rule, a threshold, the entity kinds,
or the schema changes; already-audited flags remain reproducible under the
version they were recorded with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
