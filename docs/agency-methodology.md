# Agency Methodology (v1.3.0)

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
   institution would calibrate them. They are version-stamped (see §8) so any
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

## 7. Determinism, replay, and the decision-trace eval

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
scored by the identity-resolution corroboration eval.

## 8. Reproducibility & versioning

Every run stamps the versioned decision policy into the audit trail
(`agency / agency_config`), mirroring the scoring, retrieval, critic, and
contradiction config stamps. The canonical policy for this version is below;
it is the single source of truth (`okojo.agency.agency_config`) and is
regression-tested against this document, so the doc and the code can never
silently drift.

**Version 1.3.0 — canonical policy:**

<!-- agency-config:begin -->
```json
{
  "version": "1.3.0",
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
