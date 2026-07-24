# Agency Methodology (v1.1.0)

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
   institution would calibrate them. They are version-stamped (see §7) so any
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

## 6. Determinism, replay, and the decision-trace eval

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
capability ships with its eval.

## 7. Reproducibility & versioning

Every run stamps the versioned decision policy into the audit trail
(`agency / agency_config`), mirroring the scoring, retrieval, critic, and
contradiction config stamps. The canonical policy for this version is below;
it is the single source of truth (`okojo.agency.agency_config`) and is
regression-tested against this document, so the doc and the code can never
silently drift.

**Version 1.1.0 — canonical policy:**

<!-- agency-config:begin -->
```json
{
  "version": "1.1.0",
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
    ]
  },
  "thresholds": {
    "expand_min_new_accounts": 1,
    "second_advisory_min_matches": 2,
    "re_rfi_min_contradicted": 1,
    "sufficiency_min_events": 1
  },
  "sar_bar_rule": "delegates to the Critic: clears_bar iff the bounded revision loop converged (Critique.meets_bar at the critic_config threshold)",
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
