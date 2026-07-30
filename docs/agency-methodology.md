# Agency Methodology (v1.5.0)

**Status:** synthetic-data research prototype. This document explains what
"agency" means in Okojo, why every agentic decision is deterministic, and what
each decision rule does — for an investigator, a model-risk reviewer, and an
external auditor alike.

Three principles govern everything below:

1. **Bounded, rule-based, auditable branching — never wandering.** An "agentic
   decision point" in Okojo is a pure function of the evidence state: same
   scenario, same decision trace, every time. There is no stochastic branching
   and no model-driven exploration. The deterministic backbone is itself the
   compliance feature: a reviewer can replay any run and land on the identical
   trace.
2. **Every decision is logged with its evidence.** Each decision is stamped
   into the tamper-evident audit chain (`agency / decision`) with its outcome,
   a plain-language rationale, and the evidence values that drove it. The
   LangGraph router branches on the *recorded outcome string*, so the path
   taken through the state machine and the trace in the audit log cannot
   disagree.
3. **The thresholds are tunable policy parameters, not universal truths.** The
   values here are defensible defaults for the synthetic scenario; a deploying
   institution would calibrate them. They are version-stamped (see §10) so any
   historical decision trace is reproducible.

A hard boundary above all of it: the agent **proposes, surfaces, drafts, and
flags — a human always decides and files.** No decision below sends anything,
blocks anyone, or files anything.

---

## 1. `expand_hop` — expand the network another hop?

**Question:** *is the next BFS hop worth taking, or is the frontier exhausted?*

After each hop the rule looks at three numbers: hops completed, the configured
hop cap, and how many new accounts the last hop discovered.

- `continue` — the last hop discovered at least `expand_min_new_accounts` (= 1)
  new account(s) and the cap is not reached: the frontier is productive.
- `stop_cap` — the cap is reached. The cap (default 2, hard limit 7) is the
  outer bound on how far attribution may creep; it is a policy dial, not a
  discovered fact.
- `stop_frontier_exhausted` — the last hop discovered nothing new. A further
  hop would start from an empty frontier and add nothing, so stopping here is
  **provably lossless**: the resulting graph is byte-identical to walking on
  to the cap.

**Why 1 new account is enough to continue:** a single new account can be the
controller that collapses the whole ring; discovery is cheap and bounded by
the cap, so the rule leans toward completeness *within the bound*.

## 2. `second_advisory` — pull a second advisory?

**Question:** *did more than one advisory survive the corroboration gate, and
should the runner-up be shown to the analyst?*

- `pull_second` — at least `second_advisory_min_matches` (= 2) corroborated
  matches: the ranked runner-up is **surfaced to the analyst** next to the
  primary.
- `single_match` / `no_match` — nothing further to surface.

**Boundary:** the SAR drafter consumes the *primary* match alone. A surfaced
runner-up is context for the human reviewer, never a second narrative source —
that keeps the drafted SAR's advisory basis single, citable, and unchanged by
this decision.

## 3. `re_rfi` — recommend a follow-up RFI?

**Question:** *did the contradiction checker adjudicate any claim in the
subject's RFI response as* `contradicted`?

- `recommend_re_rfi` — at least `re_rfi_min_contradicted` (= 1) claim was
  adjudicated `contradicted` (the *only* flag verdict — `qualified` and
  `unverifiable` never trigger this). For each contradicted claim the agent
  prepares **discrete, standalone routine requests** — a worklist, not a
  pre-assembled letter — one per disclosable evidence leg, each individually
  usable and each carrying its provenance citations as analyst metadata.
- `no_contradictions` / `not_applicable` — no follow-up is proposed.

**Boundary:** follow-up material is **prepared, never sent**. The human
investigator owns assembly, sequencing, and whether to put anything to a
subject at all.

### Disclosure & anti-tipping-off policy

Warning a subject that their activity is under review or has been reported —
"tipping off" — is a criminal offense under the AML regimes of, among others,
the US, UK, EU, and UAE. (Stated at the level of principle; this document is
not legal advice.) The agent's subject-facing output is therefore built to be
**structurally incapable** of it, with two layers:

1. **Safe by construction.** Requests are generated only from neutral
   administrative templates ("as part of a periodic review of your file/
   corporate records...") that cite nothing but the *may-cite* set:
   - **the subject's own transaction records** — the on-chain leg asks for the
     counterparty, commercial purpose, and settlement documentation of named
     transaction ids drawn from the subject's own rows (gas-funding and
     address-attribution rows are deliberately excluded: citing them would
     reveal tracing focus);
   - **routine corporate documentation** — the registry leg asks generally for
     the register of directors, group structure with beneficial ownership, and
     all management/service/agency/intercompany agreements, and deliberately
     does **not** name the denied entity, so the subject's inclusion *or
     omission* of the relevant agreement is itself informative;
   - **the subject's own prior responses** — the prior-RFI leg quotes the
     earlier response by its reference id and asks for the referenced
     agreement (a quotable phrase is used only when exactly one clean match
     exists in the evidence; anything less falls back to a generic phrase).

   The *never-reveal* set is absolute: evidence surfaces and analysis methods,
   device/session linkage (a **device-sourced contradiction generates no
   subject-facing request at all** — the leg stays internal), wallet
   attribution or tracing focus, and any typology, suspicion, or reporting
   status.
2. **Fail-closed validation.** Every rendered request must pass
   `assert_no_tipping_off` — a case-insensitive, stem-based screen over both
   tipping-off vocabulary (SAR/STR, suspicious, reported, sanctions,
   investigation, "under review", ...) and tradecraft vocabulary (evidence
   surfaces, device/fingerprint, structuring/layering, typology terms,
   advisory ids, ...) — run on the **fully rendered** text, after
   interpolation, because an interpolated value is the likeliest smuggling
   path. A request that trips the screen is **suppressed and flagged for human
   authoring — never emitted.**

The boundary runs between audiences, not topics: internal artifacts — the SAR
narrative, the contradiction table, the case package, the decision rationales
— legitimately use the real vocabulary and are out of the validator's scope.
Text meant for a subject's eyes never is.

## 4. `sufficiency` — is the evidence sufficient to draft?

**Question:** *can a fail-closed draft attempt even ground its opening facts?*

- `sufficient` — the subject account resolved and at least
  `sufficiency_min_events` (= 1) grounded timeline event exists: "who" and
  "when" are citable, which is the minimum the fail-closed drafter needs.
- `insufficient` — the case is **referred to a human** with the gap named. No
  draft is attempted; nothing is fabricated.

**Why so low a bar?** The drafter is already fail-closed (every claim must
resolve to a real evidence row, and rubric gaps are flagged, never invented).
The sufficiency gate is a *floor* under that machinery, not a duplicate of the
Critic: it stops the degenerate case where a draft could not cite its own
subject, and leaves quality judgment to the rubric.

## 5. `sar_bar` — does the SAR clear the bar?

**Question:** *did the bounded Critic revision loop converge on full rubric
coverage?*

- `clears_bar` — the loop converged (`Critique.meets_bar` at the versioned
  `critic_config` threshold).
- `human_review` — coverage fell short; the unmet rubric elements are named
  and the draft is flagged for human review.

This decision **delegates** to the SAR Critic rather than owning a second
quality bar — one rubric, one threshold, one version stamp (`critic_config`).
Either way the case is packaged and a human reviews it; `sar_bar` records the
disposition, it does not file.

## 6. `corroboration` — is a name match the designated party, or a collision? (Part II)

**Question:** *once a customer's name matches a designation (directly or via a
romanization variant), do their KYC identity attributes corroborate that they
ARE the designated party — or is this a same-name collision?*

This is the one decision point that lives in the **Designation-Triggered
Remediation Sweep**, not the case pipeline. A name match — especially a
cross-romanization one — is never enough to assert identity; sanctions
screening's core false positive is two different people who legitimately
romanize to the same name. `corroboration` compares the matched customer's KYC
identity attributes against the identifiers the sanctions list published for
the designated party, per hard field:

- `corroborated_true_hit` — the document number matches, **or** both date of
  birth and nationality match. A strong unique-identity signal; surfaced as a
  likely true match for an officer to confirm.
- `name_only_dismissed` — two or more hard identifiers (date of birth,
  nationality, document number) **actively** mismatch: a provably different
  person. Dismissed as a name-only collision, **with the mismatched fields
  recorded** — the dismissal and its reason are a first-class audit artifact,
  not a silent drop.
- `possible_match_needs_human` — neither corroborated nor disqualified (for
  example, a name-only foreign listing that published no date of birth or
  document number, so nothing confirms and nothing rules out). Routed to a
  human to resolve.

An identifier absent on either side is read as **unknown**, never as a
mismatch — a listing cannot be disqualified for omitting a field it never
published. Every disposition is a REVIEW-tier proposal: the sweep proposes,
records the comparison and its provenance (the KYC row and the identifier row),
and a human decides. Because the sweep has no downstream branch to route, the
outcome drives review triage, not control flow — it is a **recorded decision,
not a routing branch** (see `docs/identity-methodology.md`), so the sweep stays
a linear pipeline while still stamping each corroboration into its chain.

## 7. `geo_action` — what to propose for a surfaced geo dossier? (Part III)

**Question:** *for a **territory** designation, once an account is surfaced by
the geo triangulation, how strong is the totality — and what is the honest
proposal?*

This is the second decision point that lives in the **Designation-Triggered
Remediation Sweep**, and it applies only to the new **territory** designation
kind (a geography, not a party — see `docs/geo-methodology.md`). The one-signal
rule surfaces any account with a single positive location signal; `geo_action`
answers the separate question of *what to do about it*, from the **totality**
dossier rather than any one signal.

The dossier is scored into a **net presence score** `N`:

- **each positive location signal adds its weight**, by weight class —
  `high_value` = 3 (a region-locked carrier, or a VPN-slip: a distinctive
  locator), `standard` = 2 (an ordinary IP hit, a phone prefix, a KYC-issuing
  geography, a declared residence), `weak` = 1 (a device timezone, a coarse
  locator many regions share);
- **counter-evidence subtracts**, by staleness status — a residency document
  issued *outside* the territory argues against presence: `valid` = −3 (full
  weight), `expired` = −1 (degraded), `missing` = 0 (a missing refresh is a
  control gap, never counter-evidence). **Staleness only degrades the
  subtraction; expiry is never read as presence, so it never *adds* to `N`.**
  VPN markers are obfuscation records and are never scored.

`N` maps to one of five REVIEW-tier proposals by band:

| net score `N` | proposal |
|---|---|
| `N ≤ 0` | `no_action_totality_resolves` — the signal is rebutted by valid counter-evidence; **no restriction is proposed, but the account still surfaces for human review with its full dossier** (a resolved review, never a silent dismissal) |
| `0 < N ≤ 2` | `propose_edd_rfi` — an enhanced-due-diligence identity/geography RFI: the honest ask when the totality is present but cannot resolve |
| `2 < N ≤ 4` | `propose_withdrawal_only_restriction` |
| `4 < N ≤ 7` | `propose_trade_and_withdrawal_block` |
| `N > 7` | `propose_full_block_and_escalate` |

**Signal quality is the whole point.** A VPN-slip (`high_value`) outweighs an
ordinary IP hit (`standard`), so a lone slip proposes a restriction where a lone
ordinary IP proposes only an RFI; a region-exclusive carrier is a **full**
signal on its own, not a weak hint. And the counterweight is what lets a single
strong signal *resolve*: a lone VPN-slip (3) rebutted by a **valid** foreign
residency card (−3) nets 0 → no action; the **same** slip against an **expired**
card (−1) nets 2 → an EDD RFI (the stale document cannot rebut it, so the honest
move is to ask). The ambiguous traveller is not special-cased — the rule scores
his dossier like any other, and flipping his residency card from expired to
valid moves the proposal off the RFI by arithmetic alone.

**Boundary:** every outcome is a **proposal for a human** — an RFI is *drafted,
never sent*; a restriction/block/escalation is *proposed, never executed*. Like
`corroboration`, `geo_action` is **recorded, not routed**: the sweep has no
branch to take, so the outcome drives review triage, not control flow.

## 8. `counterparty_lifecycle` — what to propose for a designated-counterparty relationship? (Part IV)

**Question:** *after a counterparty **service** is designated, once the flow
sweep surfaces a customer who dealt with it **after** the designation, what
should happen to that relationship?*

This is the third decision point that lives in the **Designation-Triggered
Remediation Sweep**, and it applies only to the new **counterparty_service**
designation kind (a designated VASP/exchange, not a party or a geography). The
flow sweep already surfaces exposed customers and the S3 `exposure_timing` flag
already splits pre- from post-designation dealing; `counterparty_lifecycle`
answers the separate question of *what to do about the relationship* for a
post-designation dealer.

The disposition follows **strict precedence** over three booleans the wiring
computes from evidence in hand:

| precedence | condition | outcome |
|---|---|---|
| 1 (highest) | `repeat_offender` — a **prior** acknowledged designated-counterparty relationship exists, so this new exposure is a repeat | `propose_offboard` |
| 2 | `acknowledged AND stop_verified` — the customer acknowledged **this** counterparty's designation, and no dealing with its addresses is recorded **after the acknowledgment date** | `propose_unblock` |
| 3 (default) | otherwise (acknowledgment and/or a verified stop is absent) | `hold_pending` |

**Recidivism dominates.** A repeat offender who *also* acknowledged this
counterparty and stopped dealing still gets `propose_offboard` — an
acknowledgment does not reset a prior acknowledged relationship. The precedence
is proven by a constructed fixture, exactly this case.

**The hard rule of this part — no auto-unblock.** Every outcome is a
**proposal for a human**. No code path in the sweep or the lifecycle module
mutates a hold: `propose_unblock` exists ONLY as a proposal record, gated on a
verified acknowledgment **and** a verified stop, and a test proves the pipeline
cannot write to either sanctions-hold table. This is deliberate — the
real-world failure mode is an auto-unblock that investigators had to override
per case; Okojo builds the opposite. Like `corroboration` and `geo_action`,
`counterparty_lifecycle` is **recorded, not routed**.

**Subject-facing surface.** A post-designation dealer is also drafted a
customer notification (a Terms-and-Conditions matter). Its sayable scope is
**widened but bounded**: the counterparty's *public designation* and the
customer's *contractual obligation* are sayable (a designated counterparty is a
public fact and the T&C give a legitimate reason to write); the evidence
methods, the existence of any investigation, and any law-enforcement interest
are **not**. The notification is authored guard-safe — "designated / listed
counterparty", "under the Terms", never "sanctioned / blocked / reported" — and
is still validated fail-closed by `assert_no_tipping_off` on the rendered text
(defense in depth). It is `drafted_pending_human_review`, never sent; a failing
draft is suppressed and surfaced. (The full guard-surface map lands with the
Part IV posture doc.)

## 9. Determinism, replay, and the decision-trace eval

Every rule takes only explicit evidence values (counts, verdicts, coverage) —
never a ground-truth label, never a subject or claim id. Each
`DecisionRecord` carries two renderings of the same decision: `rationale`
(the audit-exact technical wording) and `plain_language` (the same decision
in compliance-officer terms, for the investigator reading the screen or the
case package) — both deterministic functions of the same evidence. The full
trace for a run is: the ordered `DecisionRecord`s in the case result, each
mirrored by an `agency / decision` audit stamp whose JSON round-trips to the
in-memory record. The decision trace is evaluated against a committed
expected-decision key (exact match, scored as precision/recall/F1 over
`(subject, decision, outcome)` triples), the same way every other Okojo
capability ships with its eval. The `corroboration` decision (Part II) is
stamped and round-tripped the same way, into the remediation sweep's chain, and
scored by the identity-resolution corroboration eval; the `geo_action` decision
(Part III) likewise, scored by the geo-action eval; and the
`counterparty_lifecycle` decision (Part IV) likewise, scored by the
counterparty-lifecycle eval.

## 10. Reproducibility & versioning

Every run stamps the versioned decision policy into the audit trail
(`agency / agency_config`), mirroring the scoring, retrieval, critic, and
contradiction config stamps. The canonical policy for this version is below;
it is the single source of truth (`okojo.agency.agency_config`) and is
regression-tested against this document, so the doc and the code can never
silently drift.

**Version 1.5.0 — canonical policy:**

<!-- agency-config:begin -->
```json
{
  "version": "1.5.0",
  "decision_points": {
    "expand_hop": [
      "continue",
      "stop_cap",
      "stop_frontier_exhausted"
    ],
    "second_advisory": [
      "pull_second",
      "single_match",
      "no_match"
    ],
    "re_rfi": [
      "recommend_re_rfi",
      "no_contradictions",
      "not_applicable"
    ],
    "sufficiency": [
      "sufficient",
      "insufficient"
    ],
    "sar_bar": [
      "clears_bar",
      "human_review"
    ],
    "corroboration": [
      "corroborated_true_hit",
      "possible_match_needs_human",
      "name_only_dismissed"
    ],
    "geo_action": [
      "no_action_totality_resolves",
      "propose_edd_rfi",
      "propose_withdrawal_only_restriction",
      "propose_trade_and_withdrawal_block",
      "propose_full_block_and_escalate"
    ],
    "counterparty_lifecycle": [
      "propose_unblock",
      "propose_offboard",
      "hold_pending"
    ]
  },
  "thresholds": {
    "expand_min_new_accounts": 1,
    "second_advisory_min_matches": 2,
    "re_rfi_min_contradicted": 1,
    "sufficiency_min_events": 1
  },
  "sar_bar_rule": "delegates to the Critic: clears_bar iff the bounded revision loop converged (Critique.meets_bar at the critic_config threshold)",
  "corroboration_rule": "compares a name/variant-matched customer's KYC identity attributes against the designation's published identifiers, per hard field (date of birth, nationality, document number): corroborated_true_hit iff the document number matches or both date of birth and nationality match; name_only_dismissed iff two or more hard identifiers actively mismatch (a provably different person, reason recorded); otherwise possible_match_needs_human. An absent field on either side is UNKNOWN, never a mismatch. Recorded into the remediation-sweep chain; it drives review triage, not control flow",
  "geo_action_rule": "the seventh decision point, in the remediation sweep, for a TERRITORY designation: each surfaced account's geo totality dossier is scored into a net presence score N = the sum of its signal weights (by weight class) minus the sum of its counter-evidence subtractions (by staleness status). Document staleness only degrades the subtraction; it never adds to N (expiry is never read as presence), and VPN markers are never scored. N is mapped to a proposal by band (see geo_action_bands): a rebutted signal (N<=0) proposes no action but the account still surfaces for human review with its full dossier; a single ordinary signal proposes an enhanced-due-diligence RFI (the honest ask when the totality cannot resolve); stronger totalities propose a withdrawal-only restriction, then a trade-and-withdrawal block, then a full block and escalation. Every outcome is a REVIEW-tier PROPOSAL for a human — nothing is executed. Like corroboration it is recorded, not routed",
  "geo_action_weights": {
    "signal_weights": {
      "high_value": 3,
      "standard": 2,
      "weak": 1
    },
    "counter_weights": {
      "valid": 3,
      "expired": 1,
      "missing": 0
    }
  },
  "geo_action_bands": [
    {
      "outcome": "no_action_totality_resolves",
      "net_at_most": 0
    },
    {
      "outcome": "propose_edd_rfi",
      "net_at_most": 2
    },
    {
      "outcome": "propose_withdrawal_only_restriction",
      "net_at_most": 4
    },
    {
      "outcome": "propose_trade_and_withdrawal_block",
      "net_at_most": 7
    },
    {
      "outcome": "propose_full_block_and_escalate",
      "net_at_most": null
    }
  ],
  "counterparty_lifecycle_rule": "the eighth decision point, in the remediation sweep, after a counterparty SERVICE is designated: a post-designation-exposed customer's relationship with the designated counterparty is dispositioned by strict precedence — propose_offboard iff the customer is a repeat offender (a prior acknowledged designated-counterparty relationship plus this new post-designation exposure: recidivism dominates and an acknowledgment does not reset it); else propose_unblock iff the customer both acknowledged this counterparty's designation AND a verified stop holds (no dealing with the counterparty's addresses is recorded after the acknowledgment date); else hold_pending (acknowledgment and a verified stop are both required to propose lifting the hold, and at least one is absent). Every outcome is a REVIEW-tier PROPOSAL for a human — no hold status is ever mutated; unblock exists only as a proposal record. Like corroboration and geo_action it is recorded, not routed",
  "decision_provenance": "each stamped decision carries row-level citations where its inputs are row properties (expand_hop: accounts discovered last hop; second_advisory: the matches' evidence rows; re_rfi: the contradicted claims' assertion+rebuttal rows; sufficiency: the subject account row); aggregate-input decisions (sar_bar, and cap/frontier stops) carry none and are covered by the aggregates' own audit stamps",
  "boundaries": {
    "second_advisory": "surfaced to the analyst only; the SAR drafter consumes the primary match alone",
    "re_rfi": "discrete routine requests are prepared for the human investigator, who owns assembly and sending; the agent never sends anything",
    "insufficient_evidence": "the case is referred to a human; no draft is attempted and nothing is fabricated"
  },
  "followup_disclosure": {
    "may_cite": [
      "routine corporate documentation requests",
      "the subject's own prior responses",
      "the subject's own transaction records"
    ],
    "never_reveal": [
      "device or session linkage",
      "evidence surfaces or internal analysis methods",
      "typology, suspicion, or reporting status",
      "wallet attribution or tracing focus"
    ],
    "validator": "assert_no_tipping_off: fail-closed on every rendered subject-facing request; a failing request is suppressed and flagged for human authoring, never emitted"
  }
}
```
<!-- agency-config:end -->

Bump `version` whenever any threshold, outcome set, or rule changes;
already-audited decision traces remain reproducible under the version they
were recorded with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
