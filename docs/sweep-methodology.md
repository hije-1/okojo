# Remediation-Sweep Methodology (v1.1.0)

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
  object with exactly the published fields — unknown fields are rejected, every
  address a clean token, both dates (`designation_date`, `listed_since`) ISO,
  and `list_type` / `obligation_vs_signal` drawn only from the published
  vocabularies.
- **The address list is conditionally required.** An empty
  `designated_addresses` is permitted for exactly one combination — a
  `national_ct` entry carrying a `signal` (a name-only foreign listing with no
  on-chain identifiers, surfaced by the name screen for identity review). Every
  other combination — and in particular any `sdn_style` / `obligation`
  designation — must carry at least one address, so a domestic designation can
  never arrive addressless and silently sweep nothing. The rule is
  negative-tested both ways.
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

## 2. Source lists — the published registry, and visible absence

Every designation now records **which list it came from and when**:
`source_regime` keys a published **list-source registry** in `sweep_config()`;
`list_type` (`national_ct` | `sdn_style` | `un_style`) and
`obligation_vs_signal` (`obligation` | `signal`) record the entry's standing;
`listed_since` records when the source list first carried it.

**The registry is explicit, versioned, stamped per run.** It names each regime
the sweep can screen against, its list type, its default standing, an ingestion
provenance note, and — critically — an explicit `ingested` flag:

| regime | list type | default standing | ingested |
|---|---|---|---|
| `SYN-DOMESTIC-OFAC` | `sdn_style` | `obligation` | **yes** |
| `SYN-FOREIGN-NCT` | `national_ct` | `signal` | **yes** |
| `SYN-UN-CONSOLIDATED` | `un_style` | `obligation` | **no** |

**Visible absence — the living demonstration.** The `SYN-UN-CONSOLIDATED`
regime is *declared and not ingested*. That fact is published here and stamped
into every sweep's audit chain (the registry rides inside `sweep_config`), so
the set of lists the sweep screened on a given date is always a documented,
reproducible fact. Absence is **stated, never inferred from an empty result**:
a reviewer never has to wonder whether a list was clean or simply never loaded.

**Signal is not obligation.** A `national_ct` listing is ingested as a
**timestamped risk signal**, never as a legal effect binding this synthetic
exchange. That distinction is load-bearing downstream: foreign-signal exposure
is surfaced for review in signal language, and asserting the legal effect of a
foreign listing is forbidden by a calibrated-language check.

### 2a. The KYC required-artifact standard

The same visible-absence discipline applies to onboarding artifacts.
`sweep_config()` publishes a per-entity-type **required-artifact standard**
(`individual` requires a `government_id` and a `proof_of_address`; `company` a
`certificate_of_incorporation` and a `beneficial_ownership` record). Because
the standard is versioned and stamped, what counts as a KYC gap on a given date
is a published policy rather than an implicit one — a required artifact removed
from the standard changes what is flagged, provably and on the record. The
standard is declared here and consumed by the KYC-completeness worksheet flag.

### 2b. Cross-list early warning — signal, not obligation

A foreign `national_ct` entry is ingested as a **timestamped risk signal**. Two
things follow, both test-enforced:

- **Lead time is measured, not assumed.** Each designation carries a
  `listed_since`; the lead-time window is `[listed_since, designation_date]`.
  For a domestic `sdn_style` entry the two are equal (zero window). For a
  foreign entry over a wallet already in the network, `listed_since` can predate
  the domestic designation by years — and the sweep measures the flow that moved
  **while only the foreign list knew** (the counterparties whose transactions
  fall inside the window, and the value that landed on the designated wallet).
  That is the early-warning number: the cost of the domestic list arriving late.
- **A name-only listing is additive, not duplicative.** A foreign entry may
  carry a name and **no wallet** (the conditional empty-address path). It never
  produces flow exposure; it is surfaced by the name screen as a **review-tier
  identity row** for an account that appears in no exposure set at all — foreign
  coverage the address-first sweep would otherwise miss entirely.

**Calibrated-language ban.** Signal-type output — worksheet statements and
escalation bodies for a foreign listing — may never **assert a legal effect**
("is sanctioned", "must be blocked", "legally required", …). The ban is a
labelled term set (the sibling of the SAR `BANNED_TERMS`) enforced at
worksheet-build time (fail-closed) and escalation-draft time (suppress-and-
surface: a violating draft is withheld **with its reason**, never silently
dropped). A foreign listing is a reason to look, with a timestamp — not an
obligation this synthetic exchange must discharge.

A **batch** entry point (`run_sweep_batch`) sweeps a whole list drop: each
designation runs through the unchanged per-designation pipeline into its own
chain, directory, and package, with a deterministic roll-up over the set. There
is no cross-designation state, so a designation swept alone and the same one
inside a batch produce byte-identical output.

## 3. Exposure semantics — pinned to the answer key's own definition

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

## 4. Designated-name screening

Registered account names are fuzzy-matched (RapidFuzz `WRatio`) against the
designated name, catching the transliteration-variant evasion an exact-match
screen misses. The threshold (85) mirrors the SDN screener's published
threshold and separation argument, but is pinned in `sweep_config()` as its
own policy parameter — a screener retune can never silently move sweep
behaviour without a version bump here. A name match is a *screening lead*
carrying its account row; it neither creates nor is required for exposure.

## 5. Block-status verification — the reconciliation gap

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

## 6. Triage worksheet & drafted escalations

The worksheet is the sweep's per-account deliverable: one row per surfaced
account (exposed or adjacent-review-only), carrying the exposure evidence,
BOTH hold statuses, any gap, the internal-tag flag, a recommended action, and
provenance for every fact its statement asserts.

**Action assignment is a fixed rule over the row's own fields** — one action
per row, from the published vocabulary:

| row | condition | recommended_action |
|---|---|---|
| exposed | has a reconciliation gap | `flags_reconciliation_gap` (the hold state must be trued up before any new action is meaningful) |
| exposed | blocked in both systems | `proposes_confirm_existing_hold` |
| exposed | otherwise | `proposes_designation_hold_review` |
| adjacent | carries an internal tag | `flags_internal_tag_for_review` (the tag is itself a finding — flagged, never obeyed) |
| adjacent | otherwise | `flags_for_review_non_flow_linkage` |

**Triage order** is the published `(action_severity, -exposure_usdt, hops,
uid)` — severity is the action's position in the vocabulary; adjacency rows
(no hop distance) sort after any real hop count within their band.

**Grounding is fail-closed at build time.** Every row must carry at least one
provenance pointer and every pointer must resolve to a real evidence row —
through the SAME `GroundingResolver` the SAR drafter uses (one membership
definition serves both pipelines). A worksheet that cannot fully cite itself
is not emitted at all.

**Escalations are drafted, never sent.** For each worksheet account with a
gap, and each exposed account with no hold in either system, an
internal-to-compliance draft is prepared for the human remediation owner —
who owns assembly, judgment, and any sending; no send path exists in this
codebase, and every draft carries `drafted_pending_human_review` as its only
possible status. Before a draft is emitted it must be grounded, resolve, and
pass the SAR calibration term check (`BANNED_TERMS`); a draft that fails is
**suppressed and surfaced with its reason** — flagged for human authoring,
never silently dropped. (`assert_no_tipping_off` deliberately does not apply:
it guards subject-facing text, and Phase 8 produces none.) Escalations are
worksheet-scoped; the full-ledger gap list rides separately on the sweep
result.

## 7. Evaluation — what the numbers do and do not claim

The sweep's exposure classification is scored against
`ground_truth.json`'s designation keys. Read that scorecard for what it is:
**a dual-implementation consistency check.** The sweep engine and the
generator's answer-key helper are two independent implementations of the same
published semantics (§3), so recall/false-positive agreement between them is
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
each gap's direction fields, and the worksheet eval asserts full grounding
coverage — every row and every escalation cites only evidence that resolves —
alongside a fabricated-pointer negative control.

## 8. The remediation package — built ON the chain

The sweep emits one decision-ready JSON package per designation
(`sweep_package.json`), the sweep's analogue of the Case Packager, reusing
that component's two structural rules verbatim and — deliberately — with **no
second version constant**: the packaging policy already published in
`packager_config()` (`docs/packager-methodology.md`) governs both packagers,
so the package embeds `package_version` from that shared source and this
document fixes the sweep package's *shape* rather than minting a new versioned
config.

- **References, never re-derivations.** The package's audit block lists each
  chain record as `(seq, actor, action, hash)` plus the tip hash and the
  verification result, captured *before* the `packaged` stamp — a record
  cannot contain its own hash — so the block covers every record through
  `sweep_complete`, and the chain is then one longer once the `packaged`
  stamp carries the package file's SHA-256. The log covers the package; the
  package pins the log.
- **Deterministic bytes.** Serialized sorted-keys / ASCII-only with
  `newline="\n"`, no wall-clock values of its own; byte-identical across two
  runs under an injected audit clock (regression-tested).

The package carries the designation, the exposed and adjacency-review accounts
with their citations, the reconciliation gaps, the full triaged worksheet, and
the drafted (never sent) plus suppressed escalations — everything the human
remediation owner needs, each fact resolving into the tamper-evident chain.

## 9. Reproducibility & versioning

Every run stamps the versioned sweep policy into its audit chain
(`remediation_sweep / sweep_config`), mirroring the scoring, retrieval,
critic, contradiction, agency, and casegraph config stamps. The canonical
policy for this version is below; it is the single source of truth
(`okojo.sweep.sweep_config`) and is regression-tested against this document,
so the doc and the code can never silently drift.

The full Part I-B config surface — the `list_source_registry`, the reserved
`action_vocabulary` entries, and the `required_artifacts` standard — is
declared here in one version bump (1.0.0 → 1.1.0) and consumed by the later
Part I-B slices with no further bump, the same discipline that declared the
`triage_order` / `action_vocabulary` fields ahead of Part I Slice C.

**Version 1.1.0 — canonical policy:**

<!-- sweep-config:begin -->
```json
{
  "version": "1.1.0",
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
    "flags_insider_staff_device_overlap",
    "proposes_confirm_existing_hold",
    "flags_foreign_signal_exposure_for_review",
    "flags_name_match_for_identity_review",
    "flags_internal_tag_for_review",
    "flags_for_review_non_flow_linkage"
  ],
  "list_source_registry": {
    "SYN-DOMESTIC-OFAC": {
      "name": "Synthetic Domestic Sanctions List (OFAC-style)",
      "list_type": "sdn_style",
      "default_obligation_vs_signal": "obligation",
      "ingested": true,
      "ingestion_provenance_note": "primary domestic designation feed; entries carry on-chain identifiers and bind the exchange (obligation)"
    },
    "SYN-FOREIGN-NCT": {
      "name": "Synthetic Foreign National Counter-Terrorism List",
      "list_type": "national_ct",
      "default_obligation_vs_signal": "signal",
      "ingested": true,
      "ingestion_provenance_note": "foreign national counter-terrorism list; ingested as a timestamped RISK SIGNAL for cross-list early warning, never as a legal obligation of this synthetic exchange"
    },
    "SYN-UN-CONSOLIDATED": {
      "name": "Synthetic UN-style Consolidated List",
      "list_type": "un_style",
      "default_obligation_vs_signal": "obligation",
      "ingested": false,
      "ingestion_provenance_note": "declared and NOT ingested in this prototype — published here and stamped into every sweep so its absence is a documented fact, not a silent configuration decision (visible absence)"
    }
  },
  "required_artifacts": {
    "individual": ["government_id", "proof_of_address"],
    "company": ["certificate_of_incorporation", "beneficial_ownership"]
  }
}
```
<!-- sweep-config:end -->

Bump `version` whenever an edge type, a threshold, the gap taxonomy, the
triage order, the action vocabulary, the list-source registry, or the
required-artifact standard changes; already-audited sweeps remain reproducible
under the version they were stamped with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
