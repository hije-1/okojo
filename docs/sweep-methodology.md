# Remediation-Sweep Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains Okojo's
Designation-Triggered Remediation Sweep — what happens when a new synthetic
OFAC-style designation arrives, how exposure and hold-status gaps are derived,
and why every number is reproducible — for an investigator, a model-risk
reviewer, and an external auditor alike.

Three principles govern everything below:

1. **The sweep reuses the core; it never moves it.** It reads through the same
   read-only connectors, grounds every surfaced fact in a provenance pointer,
   and writes its own fresh tamper-evident audit chain per run (under
   `data/sweeps/<designation_id>/`). The case pipeline, its LangGraph, and the
   case audit chains are untouched.
2. **A plain sequential pipeline, on purpose.** Agentic machinery belongs only
   where genuine decisions exist; the sweep has none that branch — parse,
   screen, walk, reconcile run in the same order every time. Where the case
   pipeline carries five bounded decision points, the sweep's honesty is that
   it carries zero.
3. **The sweep surfaces and flags; a human remediates.** No hold is placed,
   released, or modified by any code path — the connectors are read-only by
   construction, and every output is a *proposal* or a *flag* carrying its
   evidence.

---

## 1. The designation input — fail-closed by construction

`parse_designation()` is the sweep's input boundary and it ships closed:

- **Strict validation before anything else.** The payload must be a JSON
  object with exactly the published fields — unknown fields are rejected, the
  address list must be non-empty, every address a clean token, the date ISO.
- **`designation_id` is treated as a filesystem input.** It must match
  `^[A-Z]{3}-\d{4}-\d{4}$` — uppercase letters, digits, hyphens, nothing a
  path could interpret — and is validated *before* any path is derived from
  it, then re-checked at the point where the sweep directory is created.
- **A malformed paste is a clean rejection.** Parsing is a pure function:
  nothing is written, no directory exists, no partial audit chain is left
  behind. This boundary may face untrusted input in a later phase; it is
  built for that now.

A designation drawn from the synthetic `designations` table goes through
exactly the same model as a pasted payload — one validation boundary, not two.

## 2. Exposure semantics — pinned to the answer key's own definition

The sweep owns its exposure walker: one reverse adjacency over the full
transaction ledger, one multi-source BFS from the designated address set.

- **Flow edges are exactly `{transaction, controls}`** — a value transfer, or
  the fact (from the address-book table) that an account controls a wallet.
  A gas-funding link is a control *tell*, never a value flow, so it can never
  fabricate exposure. These are the same money-flow semantics as the On-chain
  Risk Scorer's exposure membership and the generator's ground-truth helper.
- **Hop distance** = the minimum number of *transaction* edges on a directed
  path from the subject (its uid or any wallet it controls) to a designated
  address. `hops = 0` means the subject controls a designated address
  outright.
- **Direct exposure** ⇔ `hops <= 1`: the subject controls a designated
  address, or a single transaction of its lands on one. Everything else
  exposed is indirect.
- **Tainted amount** — a triage size signal, not a legal quantum: at
  `hops = 0`, the total value transacted through the controlled designated
  address; at `hops >= 1`, the total of the subject's own first-leg
  transactions that start a shortest path toward the designated set. The
  transactions summed are exactly the rows cited.
- **Provenance:** every exposed account cites the address rows proving
  control and/or its own first-leg driving transactions.

**Adjacency is not exposure.** Accounts linked to an exposed account only by
a shared `device_fingerprint` or a reused KYC document are surfaced on a
separate review-only list — the same discipline as the scorer's
`gas_only_link`: linkage is a reason to look, never a flow. An account
carrying an internal "do-not-block" style tag is flagged for review like any
other; the tag exempts nothing (it is itself a finding, per the standing rule).

## 3. Designated-name screening

Registered account names are fuzzy-matched (RapidFuzz `WRatio`) against the
designated name, catching the transliteration-variant evasion an exact-match
screen misses. The threshold (85) mirrors the SDN screener's published
threshold and separation argument, but is pinned in `sweep_config()` as its
own policy parameter — a screener retune can never silently move sweep
behaviour without a version bump here. A name match is a *screening lead*
carrying its account row; it neither creates nor is required for exposure.

## 4. Block-status verification — the reconciliation gap

Two mock systems hold sanctions-hold status: `sanctions_hold_admin` (the
operational system of record) and `sanctions_hold_warehouse` (the analytics
feed copy). The sweep reconciles the FULL tables — every account, both
systems — and flags every disagreement with both rows cited.

**Gap taxonomy:**

| gap_type | warehouse | admin | reading |
|---|---|---|---|
| `missed_sync_block` | `no_hold` | `blocked` | ops placed a hold; the feed never synced it — analytics (and anything built on it) believes the account is unblocked |
| `unrecorded_unblock` | `blocked` | `no_hold` | a hold was quietly released in the system of record; the release never synced back — analytics still shows a block that no longer exists |
| `missing_in_warehouse` / `missing_in_admin` | — | — | defensive: an account present in only one system (the synthetic tables have full coverage; these types exist so a coverage failure could never pass silently) |

**Timeline note (the planted scenario).** Both planted hold actions predate
the designation: they are legacy screening actions from earlier reviews, and
the two gaps are pre-existing synchronization failures that the sweep
*surfaces* when the designation triggers the look. The designation causes the
inspection, not the holds — the dates in the synthetic tables are consistent
with exactly that reading.

## 5. Evaluation — what the numbers do and do not claim

The sweep's exposure classification is scored against
`ground_truth.json`'s designation keys. Read that scorecard for what it is:
**a dual-implementation consistency check.** The sweep engine and the
generator's answer-key helper are two independent implementations of the same
published semantics (§2), so recall/false-positive agreement between them is
a consistency property of this synthetic world — not a field-performance
claim about real ledgers.

The evidentiary weight sits in the named traps, each a designed way for a
wrong implementation to fail loudly:

- **the decoy designation** (a themed name and two addresses that touch
  nothing in the ledger) must produce the empty set — the false-positive
  probe;
- **the legacy-exposure account** (exposed under the Phase-2 sanctions key
  but with no flow to the newly designated pair) must NOT appear — a sweep
  that replays the old answer key fails here;
- **the recidivist** (whose flow dead-ends at a wallet with no outbound
  path) must NOT appear — name history is not flow;
- **the internally-tagged account** (device-linked only) must appear ONLY on
  the review-only adjacency list, with its tag flagged, never obeyed.

The gap-detection eval likewise asserts the exact planted gap set, including
each gap's direction fields.

## 6. Reproducibility & versioning

Every run stamps the versioned sweep policy into its audit chain
(`remediation_sweep / sweep_config`), mirroring the scoring, retrieval,
critic, contradiction, agency, and casegraph config stamps. The canonical
policy for this version is below; it is the single source of truth
(`okojo.sweep.sweep_config`) and is regression-tested against this document,
so the doc and the code can never silently drift.

The `triage_order` and `action_vocabulary` fields are declared here and
consumed by the triage/worksheet stage (Part I Slice C); the config is
declared complete now so the version does not bump mid-phase.

**Version 1.0.0 — canonical policy:**

<!-- sweep-config:begin -->
```json
{
  "version": "1.0.0",
  "flow_edge_types": ["controls", "transaction"],
  "hop_semantics": "hops = minimum number of transaction edges on a directed path from the subject (its uid or any wallet it controls) to a designated address; 0 = the subject controls a designated address",
  "direct_hop_max": 1,
  "adjacency_link_types": ["reused_kyc", "shared_device"],
  "name_match_threshold": 85,
  "hold_systems": {
    "system_of_record": "sanctions_hold_admin",
    "analytics_copy": "sanctions_hold_warehouse"
  },
  "gap_taxonomy": {
    "missed_sync_block": "admin blocked, warehouse no_hold (feed never synced the block)",
    "unrecorded_unblock": "warehouse blocked, admin no_hold (release never synced back)",
    "missing_in_warehouse": "account absent from the warehouse feed copy",
    "missing_in_admin": "account absent from the admin system of record"
  },
  "triage_order": ["action_severity", "-exposure_usdt", "hops", "uid"],
  "action_vocabulary": [
    "proposes_designation_hold_review",
    "flags_reconciliation_gap",
    "proposes_confirm_existing_hold",
    "flags_internal_tag_for_review",
    "flags_for_review_non_flow_linkage"
  ]
}
```
<!-- sweep-config:end -->

Bump `version` whenever an edge type, a threshold, the gap taxonomy, the
triage order, or the action vocabulary changes; already-audited sweeps remain
reproducible under the version they were stamped with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
