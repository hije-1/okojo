# Decision Log & Context Transfer

This file preserves the reasoning behind Okojo so that anyone (or any agent)
picking up the project has the full context that would otherwise live only in a
chat history. Read it before changing scope, architecture, or the data model.
Companion docs: `Strategy.md` (full write-up) and `Build-Plan.md` (dated plan).
This log records *why* each choice stands; for *who decided* — the human decision
authority behind the project — see `docs/human-decisions.md`.

_Last updated at handoff from the planning phase (Phase 0 complete)._

---

## 1. Goal & audience
A public GitHub research project by a senior crypto-compliance executive exploring
what agentic AI can do for financial-crime investigations — deep domain expertise
and hands-on agentic engineering in one build ("balance of both"). Built from
scratch, solo, ~20 hrs/week.

## 2. Scope decision — one flagship, not a suite
A single, deliberately-scoped flagship with a documented roadmap beats a
scattered set of demos: for a senior audience, choosing what to build and what to
defer *is* the signal. The flagship is an **agentic crypto-investigations
co-pilot** ("Okojo") that fuses several top pain points under one narrative.

## 3. How capabilities were chosen
Ten candidate pain points were scored 1–5 on six dimensions: **Data** (buildable
with public/synthetic data), **Build** (solo-feasible), **Agentic** (real
tool-use/reasoning, not a classifier), **Domain** (compliance/FIU sophistication),
**Safe** (publishable — no PII/opsec/reputational hazard), **Distinct**
(distinctiveness). Top tier: network/cluster mapping, SAR quality, unified subject
timeline, multilingual OSINT. Full table in `Strategy.md`.

## 4. Expert-review fixes (applied to the design)
A dual AI-architect / crypto-compliance review produced eight fixes, all now
baked into the plan:
1. **Name the agentic decision points** vs. the deterministic backbone; frame the
   determinism as a compliance/auditability feature.
2. **Add an evaluation harness** (precision/recall vs. labels; SAR-quality rubric;
   advisory-match FP rate; ablations). This is why the generator emits
   `ground_truth.json`.
3. **Elliptic↔OFAC address-space correction:** Elliptic's anonymized nodes do NOT
   line up with OFAC's real crypto addresses. Keep Elliptic for the
   graph/illicit-classification capability; use an *explicitly labeled synthetic
   address-tagging layer* for OFAC-style sanctions matching. Never conflate the two.
4. **SAR grounding contract:** the drafter may assert only facts traceable to a
   retrieved record; provenance pointers; schema-validated; reject uncitable claims.
5. **Operationalize the SAR "quality" rubric** against FinCEN's narrative
   expectations (who/what/when/where/why/how; predicate offense; subject & network;
   on-chain evidence).
6. **Calibrate language** (proposes/surfaces/drafts, not "instantly/autonomously").
7. **Right-size the MVP** to a walking skeleton first, then thicken.
8. **Broaden the regulatory frame** (STR vs. SAR, FATF Travel Rule, EU AMLD/MiCA)
   as roadmap; leverages the builder's global background.

## 5. Typology review (patterns only, never PII)
The design was pressure-tested against publicly documented investigation
typologies — FinCEN's Iranian-oil / "shadow-banking" advisories, OFAC
designations, and published exchange enforcement actions. **We replicate
behavioral patterns, never identities, addresses, or documents.** Outcomes:
- **Promoted to headline capabilities:** the **RFI Contradiction-Checker** and the
  **Remark/Tell Miner** — in documented investigations these signals, more than
  blockchain analytics, are what crack attribution and expose false narratives.
- **Gas-funding linkage** became a named tool in the Network Expander (a move
  that repeatedly unmasks "non-custodial" controllers).
- **Persistent case graph** added for cross-case recidivism (the documented
  failure mode of an account clearing multiple prior "retain & monitor" reviews
  before being connected to a wider network).
- **New pain points identified:** PP-11 tell mining, PP-12 remediation
  sweeps, PP-13 ML alert auto-closure QA, PP-14 tokenized-commodity issuance tracing.
- **Governance capture** is the decisive documented failure mode (blocked
  investigator access, vanishing records, "internal account" shields). We frame
  the fix as a product feature: the tamper-evident audit trail + treating
  "internal account" tags as *flag-for-review, not obey*.

## 6. The synthetic demo scenario
Re-anchored on a fabricated but pattern-faithful **oil / sanctions-evasion
network** that exercises every capability and ties to public FinCEN advisories.
The generator (`src/okojo/scenario/`) plants: a shell-entity ring with cutout
directors; reused KYC docs across "separate" entities; shared devices; sanctioned-
jurisdiction IP interleaved with VPN; structured just-under round-number transfers;
gas-funded "non-custodial" hops; betraying withdrawal remarks; a licensed-trust RFI
narrative with ground-truth lies; a recidivist account; and an "internal account,
do-not-block" red herring. All labels are in `ground_truth.json`.

## 7. MVP core vs. committed v1.0 capstone vs. roadmap
Membership in v1.0 is decided on **payoff-to-*marginal*-cost, not payoff alone.**
- **MVP core:** components 1–8 (Profile Aggregator, Network Expander, Risk Scorer,
  Tell Miner, RFI Contradiction-Checker, Advisory Matcher, SAR Drafter+Critic,
  Case Packager + case graph).
- **Committed v1.0 capstone:** **PP-12 Designation-Triggered Remediation Sweep**
  (component 9). Promoted from roadmap because it is the most regulator-relevant
  capability (FinCEN's aggressive Iran program) *and* cheap to build last — it
  re-orchestrates finished components rather than adding a new subsystem.
- **Committed post-capstone: the Audit Narrator, promoted to Phase 9** (PM ruling
  2026-07-31 — see §13). The grounded summarizer over Okojo's own hash-chained
  audit trails (scoped to **all** chain families: case, sweep, and batch) makes the
  tamper-evident record *reviewable*, not just provable; low marginal cost, reuses
  the native log. Launch hardening becomes **Phase 10** (its CI slice excepted —
  CI lands as Phase 9's first slice so the narrator builds under independent green).
- **Roadmap (post-v1.0, ordered by payoff):** the **coverage-gap check** and the
  **API service facade** (both added at Phase-8 sign-off — see §19); then PP-13 (ML
  auto-closure QA) and #8 (vendor reconciliation); then PP-14 (tokenized-commodity
  tracing — kept out of v1.0 despite timeliness because it needs new
  contract-tracing tooling with little reuse), #5 (multilingual OSINT), #4/#7
  (LE-request/MLAT routing). Build these in public after launch to keep the repo
  visibly growing. (See §13, §19.)

## 8. Data sources
- **On-chain graph:** Elliptic / Elliptic++ (public, labeled BTC graph). NOTE:
  this is the **free public research *dataset*** (anonymized node IDs, no real
  addresses), **not** Elliptic's licensed product — no license is required. The
  repo never uses real crypto addresses; the OFAC-style match runs on the
  synthetic address-tagging layer (see the address-space fix in §4).
- **Fiat/crypto transactions:** IBM "Transactions for AML" (IT-AML) — start with
  the **HI-Small** variant. (AMLSim is IT-AML's *simulator* predecessor; AMLNet is a
  third-party alternative with rich per-tx metadata.)
- **Sanctions:** OFAC SDN/Consolidated lists (+ OpenSanctions structured version).
- **FinCEN advisories:** public 508-PDFs (Iran illicit-oil/shadow-banking; China CMLN).
- **Personas/devices/remarks/RFIs:** synthetic via the scenario generator (Faker).

## 9. Naming & guardrail decisions
- Device identifier is **`device_fingerprint`**, a generic internal-exchange schema term.
- Synthetic + public data only; human-in-the-loop; grounding contract; tamper-evident
  audit trail as centerpiece; calibrated language. See `CLAUDE.md` for the enforced list.

## 10. Evaluation approach
`data/synthetic/ground_truth.json` is the answer key. Every capability is scored
against it (e.g., recall of network members, precision of flagged RFI
contradictions, detection of the sanctioned-exposure sweep). Keep it in sync when
the generator changes.

## 11. Open threads / next actions
- **Phase 1 (next):** mock connectors over the synthetic data → Profile Aggregator
  (unified anomaly-flagged timeline) → minimal LangGraph orchestrator with
  append-only audit logging → tiny end-to-end flow → **publish the walking skeleton
  to GitHub.** Details in `Build-Plan.md`.
- Decide the LLM provider/model for the reasoning components (kept provider-agnostic
  so far).
- Set up the public GitHub repo + a steady public commit cadence.
- **RESOLVED (long closed; retained as the Day-0 record).** All three threads are
  done: the walking skeleton shipped and was published (Phase 1), and every phase
  through v1.1 followed; the reasoning components stayed provider-agnostic — no
  external LLM, deterministic templates throughout; the public repo and a steady
  commit cadence are established. Current status lives in `CLAUDE.md` and the
  [CHANGELOG](../CHANGELOG.md).

## 12. Licensing & contribution policy
_Added Day 3 (Phase 2 complete)._

- **MIT retained through the public research phase — deliberate.** It maximizes the
  repo's openness and reach and costs nothing long-term: the author remains the sole
  copyright holder and can relicense future versions at any time (already-published
  versions remain MIT regardless). **Revisit at the v1.0 launch** — the natural
  inflection point — where the options include relicensing future work (e.g.,
  BSL/PolyForm), open-core, or keeping the prototype MIT as the credibility layer
  for a separate commercial product.
- **Contribution policy (protects the relicensing option).** External *code*
  contributions are not accepted at this time; issues and feedback are welcome.
  Rationale: an outside contributor would hold copyright in their lines under MIT,
  and relicensing later would then require their consent. **Revisit alongside the
  license at v1.0** — a DCO or CLA would be the mechanism if PRs are ever opened.
- **RESOLVED at v1.0 (2026-07-31, PM ruling — see §20):** the v1.0 revisit is
  closed. **Keep MIT, and continue not accepting external code contributions.**
  The relicensing option is preserved (sole copyright holder; already-published
  versions stay MIT regardless). DCO/CLA machinery deliberately not adopted.
- **Superseded at v1.1 (2026-08-03 — see §21):** the reserved relicensing option
  was exercised — the license changed to BSL 1.1 for v1.1.0 and later (v1.0.0 and
  earlier remain MIT). The no-external-contributions posture is unchanged.

## 13. Audit Narrator — promoted from roadmap to committed Phase 9
_Added Day 3 (Phase 2 + Slice 4b complete); promoted to committed scope Day 10
(2026-07-31, PM ruling)._

- **Audit Narrator added to the roadmap (user-proposed).** Prioritized *ahead of
  PP-13* because it reuses Okojo's native hash-chained audit log — no new data and
  no new privacy surface — and directly strengthens the audit-trail centerpiece:
  it makes a *provable* log *reviewable*. A grounded summarizer over the log emits
  a plain-language, citation-backed narrative of what the agent did, in order, and
  why.
- **Scope broadened at Phase-8 sign-off (see §19):** Phase 8 added a second
  audit-chain family (the sweep) and a batch path, so the Narrator's scope is now
  **all** chain families — case, sweep, and batch — not the case log alone.
- **PROMOTED to Phase 9 (2026-07-31, PM ruling).** Resequenced *ahead of* launch
  hardening because it completes the audit-trail centerpiece; launch hardening
  becomes **Phase 10** (CI excepted — CI lands as Phase 9's first slice so the
  narrator builds under independent green), and no demo recording or walkthrough
  happens until the narrator is live. Design rulings, all committed:
  - **1:1 narration** — one sentence per record, with a two-register de-emphasis
    for setup records (`*_config`, `tool_call`) vs consequential actions; a
    faithful reading of the record, not a lossy summary.
  - **Templates, zero LLM** — a deterministic `(actor, action) → sentence`
    template map, so narrator output is byte-deterministic per chain and the eval
    holds. The faithful-reading rationale is recorded in the methodology doc.
  - **Verify first; a failed verification IS the narrative** — a broken chain is
    reported (the seq where it first fails, cited), never summarized past the break.
  - **Batch** narrates as N sweep-chain narratives + a roll-up summary grounded to
    the constituent sweep-chain records; the non-chained `rollup` dict is never a
    grounding source.
  - **Read-only** — the narrator writes NOTHING to any chain; all existing chains
    and capability scorecards are byte-identical by construction. Its version is
    pinned through the artifact (`narrator_config()`, `NARRATOR 1.0.0`, the 11th
    doc↔code anti-drift pair), like `packager_config` — not stamped into any chain.
- **Guardrails carry over unchanged:** the grounding contract and calibrated
  language apply — every summary sentence cites the log entries behind it
  (fail-closed on an unresolvable citation), and the `BANNED_TERMS` calibration
  guard applies to narrator output.

## 14. AI-assisted development & code provenance
_Added Day 4 (Phase 4 complete; pre-Phase-5)._

- **Decision.** Okojo is built with AI assistance (Claude Code) used as a tool
  under human direction — architecture, scope, security posture, and review are
  the author's. This is disclosed here, not hidden.
- **Why this is safe for copyright / eventual sale.** US copyright protects
  human-authored expression; AI used as a tool under human creative control does
  not forfeit protection (US Copyright Office, 2025 guidance). The author is the
  sole human author — an AI cannot be an author, so there is no co-owner to
  clear, and no vendor holds a rights stake (Anthropic assigns output rights to
  the user). The `Co-Authored-By: Claude` commit trailer is attribution metadata,
  NOT a legal assignment of any right.
- **Sole-authorship posture (preserved).** MIT-licensed for the public research phase,
  but no external PRs are merged — so the author holds copyright to all
  human-authored expression and retains the right to relicense or sell. (See §12.)
- **Lifting risk is addressed, not assumed away.** Verbatim reproduction of
  third-party code by assistants is rare and clusters on generic boilerplate
  (GitHub's own study: ~0.009% of suggestions, almost all license headers /
  standard idioms, mostly at empty-context file starts). Copyright also does not
  protect ideas, methods, or short/common snippets — so the residual concern is
  narrow, substantive verbatim expression. The Code Provenance & Originality Gate
  in the pre-publish checklist turns "believed original" into "scanned + logged":
  dependency-license audit + embedded-notice scan + distinctive-string search each
  publish, and a snippet-level SCA scan before any sale.
- **Evidence retained.** The public commit history and dated design docs are the
  primary record of human authorship and creative control — kept intact as
  ready-made diligence evidence.
- **Not legal advice.** At an actual sale, IP counsel handles reps & warranties;
  this entry records the process, not a legal opinion.

## 15. One-time scenario re-baseline: reconciling the RFI's C2 rebuttals
_Added Day 4 (Phase 5, Slice A). Companion to §14._

- **The problem.** The generator declared RFI claim C2 — *"[SHELL_NZ] is a separate
  legal entity with no ownership or management relationship"* — false, and listed
  three rebuttals: a reused KYC document, a shared device fingerprint, and a common
  controller. **None of the three was ever planted.** The reused-KYC pairs are
  SIBLING/SHELL_AE and EMPLOYEE/EMPLOYEE-2; no shared device pairs the trust with
  SHELL_NZ; and there was no corporate-registry table at all. The answer key
  asserted evidence the dataset did not contain, so the Phase-5 contradiction
  checker could not have refuted C2 from the data — it would have had to trust the
  label, which is exactly the tautology the evals exist to prevent.
- **Why the old legs could not simply be planted.** Adding either would mean adding
  rows to `accounts.csv` or `devices.csv` — frozen tables whose byte-identical
  regeneration every prior phase depends on. C2 is therefore **re-based** onto three
  sources that either already exist or arrive in new tables: the corporate
  registry's **common director** across the two entities over an overlapping
  appointment window, the subject's **own prior RFI answer** conceding a management
  services agreement, and the **bidirectional near-equal layering flows** that
  already run between the two entities' controller wallets.
- **One list, three consumers.** `_RFI_CLAIM_SOURCES` in the generator is now the
  single definition behind (a) each claim's `contradicted_by` prose, (b)
  `ground_truth["rfi_claim_key"].expected_sources`, and (c) which checkers are
  expected to fire. Guard tests pin them together, so the drift that produced this
  defect cannot recur silently.
- **C4 was already sound** — its sanctioned-exposure, structured-transfer and
  gas-funding legs all resolve to planted rows, so its claim is byte-for-byte
  unchanged. A test asserts each leg resolves.
- **Scope of the change, and how it was verified.** Eight of the nine pre-existing
  CSVs are **byte-identical**; `rfi.csv` changes in exactly one cell —
  `claims_json` → C2 → `contradicted_by` — with rows, columns, ordering, `question`
  and `response_text` unchanged, confirmed by a field-level diff rather than a file
  hash. `ground_truth.json` gains `rfi_claim_key` (all four claims, so the
  *qualified* and *unverifiable* branches have gold values, not just the lies),
  `prior_rfi_ids` and `registry_shared_officer_uids`. Two new tables,
  `registry.csv` and `rfi_prior.csv`, are built with **zero RNG draws** from
  personas, jurisdictions and dates already generated — no new identity enters the
  repo. The phase-1, phase-2 and advisory scorecards re-run with **zero delta**.
- **A one-time re-baseline, not a standing exemption.** The determinism contract is
  restored in full immediately: `test_deterministic` now byte-compares **every**
  table (including the new `rfi.csv` content and both new tables), and a companion
  test regenerates under two different `PYTHONHASHSEED` values — catching
  set-ordering nondeterminism that a same-process double-regeneration structurally
  cannot see, and which would otherwise pass locally and diverge on CI.

## 16. LangGraph adoption: determinism and offline posture under agency
_Added Day 4 (Phase 6, Slice A)._

- **Decision.** Phase 6 converts the fixed pipeline into a LangGraph state machine
  (`langgraph==0.2.45`, the pin held since Phase 0). Slice A is deliberately
  *mechanical*: every node is verbatim code motion of the corresponding stage, in
  the same order — proven by running all 12 roster subjects through the old linear
  orchestrator and the new graph with an injected audit clock and byte-comparing
  the hash-chained audit logs (12/12 identical). "Agency" arrives afterwards as
  dedicated decision nodes, never as hidden control flow.
- **Determinism is engineered, not assumed.** No checkpointer is ever
  instantiated — no UUIDs, wall clock, or state serialization enter the run path
  (this also sidesteps the checkpoint library's serialization machinery entirely;
  Okojo never stores or loads a checkpoint). The graph has no fan-out, so the
  runtime executes exactly one node per superstep in a fixed order, and a shape
  test pins the exact node/edge sets. A byte-identity test (two clocked runs →
  identical audit chains) makes the property regression-guarded, not aspirational.
- **Offline posture, verified and guarded.** The LangChain ecosystem ships an
  optional telemetry client (langsmith); it activates only via environment
  variables that Okojo never sets. A guard test clears those variables, blocks
  socket creation outright, and runs a full case end-to-end: the run path opens
  zero network sockets. An investigation co-pilot must not phone home; here that
  is a tested invariant, not a configuration hope.
- **Dependency discipline.** The install added 21 new transitive packages and
  changed **zero** existing pins (verified by a before/after freeze diff —
  pydantic, numpy, pandas et al. untouched). All new licenses are
  MIT/BSD/Apache except orjson (weak-copyleft MPL-2.0 component; transitive,
  unmodified, unvendored — the same pre-classified class as certifi, per the
  provenance-gate rule).

## 17. Second one-time re-baseline: registration-date coherence
_Added Day 6 (Phase 7, during UI polish). Companion to §15._

- **The problem.** `registration_date` was drawn as an independent random
  timestamp with no ordering constraint against the account's separately drawn
  activity. Result: 21 of 24 accounts had logins and/or transactions dated
  **before the account existed** (19 with pre-registration logins; 24
  exchange-leg and 9 controlled-address transaction legs pre-dating
  registration). Six phases of table-shaped views never read the two columns
  together; the Phase 7 Timeline rebuild rendered events chronologically and
  the impossibility was visible within seconds — spotted by the PM on the demo.
- **The fix, and why it is minimal.** An RNG-free post-pass in the generator
  (placed at the existing "everything from here on is RNG-FREE" boundary):
  each account's first observed activity is computed from values already drawn
  (logins, exchange-leg transactions, controlled-address transactions), and an
  incoherent registration is clamped to 30 days before it. Coherent draws are
  untouched (3 of 24); no draw order changes, so every activity timestamp,
  identity, and amount is byte-identical. Blast radius, verified by field-level
  diff: **one column in `accounts.csv` (21 cells), the 14 derived
  `registry.csv` date cells, and the derived `rfi_prior.csv` `asked_date` — all
  other tables, including `ground_truth.json`, byte-identical.** Rows and
  ordering unchanged everywhere.
- **Phase-5 evidence survives by construction.** The registry and prior-RFI
  dates were already *derived* from registration dates (§15's zero-RNG
  discipline), so they re-derived correctly through the existing code: the
  shared-director appointment windows still overlap, and the prior RFI still
  postdates both incorporations it references (now also pinned by test).
- **Guarded going forward.** `test_registration_dates_precede_all_account_activity`
  pins all three coherence classes plus the registry/prior-RFI derivations, so
  the defect class cannot silently re-enter. The determinism guards
  (`test_deterministic`, `test_deterministic_across_hash_seeds`) continue to
  cover the changed generator.
- **A re-baseline, not an exemption.** As with §15: the determinism contract is
  restored in full immediately, and the eval answer key was untouched — no
  metric moved (all capability scorecards re-verified after the change).
- **Known gap, recorded (Phase 7).** `PACKAGE_VERSION`
  (`src/okojo/packager/packager.py`) is the one version constant with no
  methodology doc and no doc↔code anti-drift guard, unlike the six others
  (scoring, retrieval, critic, contradiction, agency, casegraph). Deliberately
  not fixed under polish; it rides with the grounding-completeness slice, where
  the version-bump and doc-regeneration machinery is already open.
  *(Closed later in Phase 7: `packager_config()` + `docs/packager-methodology.md`
  + the seventh anti-drift test — pinned through the artifact rather than a
  seventh audit stamp, as that doc explains.)*

## 18. Grounding completeness: we measured our own headline metric and cut it
_Added Day 6 (Phase 7, Slice E)._

- **What the reliability harness found.** The grounding contract proved "every
  pointer names a real row" — not "the claim is about this subject."
  `mine_remarks` is a dataset-wide screen (correctly — attribution often breaks
  open on someone else's remark), but the drafter injected the top tells into
  every SAR unconditionally. Measured across all 14 subjects: **13 claims cited
  rows outside the subject's own network entirely** (an isolated account's SAR
  carried four tells citing ring members' transactions), and 39 more cited
  network rows without attributing them in the claim text.
- **The fix (CRITIC v1.1.0).** A drafting-policy gate,
  `tell_scope = "subject_network_closure"`: a tell enters a draft only when its
  transaction touches the subject or an account/address the expansion actually
  reached in that run. Deliberately carried in `critic_config()` under a
  nested `drafting` key — claim-*selection* policy owned by the drafter, kept
  structurally distinct from the Critic's *scoring* knobs (threshold, rubric),
  because the Critic never selects claims; it grades what it is handed.
- **The ablation went down on purpose, and that is the point.** Under v1.0.0
  the WITHOUT-Critic recall read 0.560 against a 25-element gold. The gate
  exposed one gold element — the noise role's `subject_and_network` — as
  credited entirely on borrowed evidence, so the gold was re-authored to 24
  honest elements (WITH stays P=R=F1=1.0 by construction against the honest
  key; WITHOUT moved to 0.542). **A headline metric was corrected downward
  because our own measurement found it inflated.** For the affected subjects
  the honest outcome is fewer claims and, for the isolated ones, an uncovered
  `subject_and_network` element flagged for human review — which is what a
  fail-closed system is supposed to do with evidence it does not have.
- **Decision-level provenance, and the announced audit-hash move.** Slice E
  also gave `DecisionRecord` a row-level provenance field (AGENCY v1.2.0) —
  the accounts a hop discovered, the advisory matches' evidence rows, the
  contradicted claims' assertion+rebuttal rows, the subject row behind the
  sufficiency gate; aggregate-input decisions (sar_bar) carry none, covered
  by their own audit stamps — and `RecidivismView` the citation for the
  accounts row its flag derives from (CASEGRAPH v1.1.0; the audited summary
  is unchanged). Because every decision is stamped into the hash chain via
  `summary()`, **this moves the audit-chain content — and therefore the tip
  hash and package SHA-256 — for every case, by intention and announced in
  advance**, not discovered mid-commit. The chain remains internally
  consistent and verified; determinism is re-proven by the standing two-run
  byte-identity and packager byte tests; the decision-trace eval (triples vs
  the domain-authored gold) is unchanged at P/R/F1=1.0.

## 19. Phase-8 sign-off: the calibration guard goes live; three roadmap items
_Added Day 11 (Phase 8 sign-off; component 9 complete)._

- **The SAR calibration guard now has a live call site.** `calibration_violations`
  (the over-claiming-language check: *instantly / autonomously / guaranteed /
  proven fact / definitely / certainly*) had existed since Phase 1 but was called
  only from tests — a control with the shape of enforcement but no substance,
  exactly the pathology the P8-G falsification discipline exists to catch. Ruled
  and wired: `assert_calibrated` is called fail-closed at SAR draft-validation
  time, in `build_sar` and on every revised draft in the drafter-critic loop,
  **alongside** the two-step grounding contract (`assert_grounded` /
  `assert_resolvable`). A violating draft is rejected and the offending statements
  surfaced — never silently passed.
- **Why it moved nothing.** Verified *before* wiring: every gold SAR draft across
  all 33 subjects (12 roster + 21 isolated) already has zero calibration
  violations, so the guard never fires on the scenario. Proven byte-for-byte —
  the case audit chains are identical (fixed clock) before and after the wiring,
  and the guard emits no audit record. No version moved (SAR/CRITIC/AGENCY): this
  activates an existing check, it does not change a threshold, rubric, or config.
- **Three roadmap items added (post-v1.0, see §7).** (a) **Coverage-gap check** —
  the customer base's geographic footprint measured against the enabled
  list-source regimes, surfaced as a standing signal (are we screening against the
  lists our actual exposure calls for?). **BUILT 2026-08-04 (rides on v1.1.0, not
  separately tagged): a three-leg footprint (residence + KYC-issuing + nationality)
  vs the enabled+ingested regimes, two gap classes (ingestion / no-coverage), a new
  versioned `coverage_config` + methodology doc + anti-drift pair (the 12th;
  COVERAGE 1.0.0) that READS the frozen sweep registry (SWEEP untouched), its own
  `coverage` audit-chain family narrated by the read-only Narrator (NARRATOR stays
  1.0.0), and a sweep-mode panel + case pointer. All existing scorecards
  byte-identical.** (b) **Audit Narrator scope broadened to
  all chain families** — Phase 8 added the sweep chain and the batch path, so the
  Narrator now covers case + sweep + batch, not the case log alone (§13).
  **Subsequently promoted to committed Phase 9 (2026-07-31, PM ruling — see §13);
  launch hardening became Phase 10, CI excepted.** (c)
  **API service facade** — the sweep and case pipelines are already payload-in /
  proposals-out by design (validated payloads, grounded proposals, an append-only
  audit trail between), so production exposure is connector and infrastructure
  work, not a redesign. Items (a) and (c) remain logged as scope, deliberately not
  built now — roadmap discipline holds; Phase 10 is launch hardening (security
  pass, SCA, deploy, code-systems map, recorded walkthrough last), with CI pulled
  forward into Phase 9's first slice.

## 20. v1.0 license & contribution ruling: keep MIT, no external contributions
_Added Day 11 (2026-07-31, Phase 10 Session C — at the v1.0.0 tag). Resolves the
"revisit at v1.0" placeholders left in §12._

- **Context.** §12 deliberately deferred the license/contribution question to the
  v1.0 launch — the natural inflection point. Cutting the v1.0.0 tag is that
  point, so the question was put to the PM at tag time with three options.
- **Options considered:**
  1. **Keep MIT + continue accepting no external code contributions** (the
     registered PM recommendation).
  2. **Relicense future work** — keep v1.0 MIT but place post-v1.0 work under a
     different license (e.g. BSL/PolyForm source-available, or open-core).
  3. **Adopt DCO + CLA** — open to outside contributions with a Developer
     Certificate of Origin sign-off plus a Contributor License Agreement.
- **Ruling (PM, 2026-07-31): Option 1 — keep MIT, no external contributions.**
  - **Why keep MIT.** It maximizes the repo's openness and reach at no long-term
    cost. As sole copyright holder the author can still relicense future versions
    at any time; already-published versions remain MIT regardless. MIT also keeps
    the prototype usable as a credibility layer under any later commercial product
    without foreclosing that path.
  - **Why no external contributions.** Accepting outside code would give a
    contributor copyright in their lines under MIT, and any later relicensing of
    those lines would then require their consent — so the no-contributions posture
    is what *preserves* the Option-2 relicensing choice for later. Issues and
    feedback remain welcome; only code contributions are declined.
  - **Why not DCO/CLA now.** Adopting contributor-agreement machinery only makes
    sense once inviting PRs; that is not the posture for a solo synthetic-data
    research prototype. Logged as the mechanism to reach for *if* contributions are
    ever opened (unchanged from §12).
- **Effect.** No repo-wide license change: `LICENSE` (MIT) stays as-is; the README
  states the no-external-contributions posture in calibrated terms. This ruling
  closes the §12 revisit; the relicensing option is explicitly preserved, not
  exercised.
- **RESOLVED / superseded at v1.1 (2026-08-03).** The "keep MIT" decision above
  governed the v1.0.x line and is preserved for those published snapshots. At the
  v1.1.0 release the relicensing option this ruling reserved was exercised: the
  license was changed to BSL 1.1 for v1.1.0 and later — see §21. The
  no-external-contributions posture is unchanged.

## 21. v1.1 license change: MIT → Business Source License 1.1
_Added Day 12 (2026-08-03, the v1.1.0 release session). Supersedes the "keep MIT"
ruling in §20 for v1.1.0 and later._

- **Ruling (2026-08-03).** From v1.1.0 onward Okojo does not remain MIT. The
  license is changed to the **Business Source License 1.1** (BSL 1.1,
  source-available), using the MariaDB template verbatim.
- **Parameters (PM-confirmed at the release).**
  - **Licensor:** Jennifer Hicks.
  - **Licensed Work:** Okojo v1.1.0 and later.
  - **Additional Use Grant:** non-production use — research, evaluation, and
    demonstration — is free; production or commercial use requires a license from
    the Licensor.
  - **Change Date:** 2030-08-03 (four years from the v1.1.0 release date).
  - **Change License:** MIT — each version converts to MIT on its Change Date.
- **v1.0.0 and earlier are unaffected.** Those published snapshots remain under
  the MIT License; that grant is irrevocable and is not withdrawn by this change.
- **Contribution posture unchanged** from §20: issues and feedback remain welcome;
  external code contributions are not accepted.
- **Effect.** `LICENSE` is replaced with the BSL 1.1 text; the README license
  section, `SECURITY.md`, and the three status surfaces state the split (v1.1.0+ =
  BSL 1.1; v1.0.0 and earlier = MIT) in calibrated terms. GitHub's license
  detector reports BSL-1.1 from this release forward.

## 22. Two-record transaction data model: exchange records vs. chain records
_Added Day 12 (2026-08-05; rides on v1.1.0, no version move). Ratifies D-079._

- **The problem (a realism flaw, caught on the live demo).** The prior model was
  one transaction row per value movement, and that single row carried both the
  on-chain endpoints and a free-text `remark`. A live-demo review saw an on-chain
  transfer rendered with a customer's free-text note — which a real chain transfer
  cannot carry (a token transfer is address → address, with no memo field). The
  one-row model had conflated two different objects: the exchange's **internal**
  record of a customer's instruction (which legitimately carries free text) and
  the **on-chain** settlement of it (which never does).
- **Why the simple fix was rejected under stop-on-drift.** The obvious band-aid —
  relabel the offending row as internal-only so it may keep its remark — was
  proven to sever the exposure path the whole scenario turns on: the
  shell → trust → hop → sanctioned walk depends on that movement being *on-chain*,
  so demoting it collapsed the exposed set 8 → 3. Under the standing
  byte-identity discipline that is a stop-and-show, not a quiet edit, so the
  one-row route was halted and the model fixed properly instead (D-079: fix it
  right, even across sessions, over any band-aid).
- **The model (Option 4).** One transaction table gains a `record_kind`
  discriminator (`"exchange"` | `"chain"`) plus settlement links (`settlement_ref`
  / `settled_by`). Each value movement is an exchange record (a customer-attributed
  `uid:` leg, which may carry a remark) and, where it settles on-chain, a chain
  record (address → address, which may **never** carry a remark — enforced at
  generation). The author supplied the binding domain constraint from operational
  experience: customer **withdrawals settle on-chain from a single omnibus hot
  wallet, never from a customer-attributed address**; a new hot wallet
  (`addresses.csv`) is the source of every withdrawal settlement leg.
- **Customer free text moves to its realistic home.** The two betraying tells that
  used to live on chain remarks relocate to a new `address_book.csv` — the
  customer's own saved / whitelisted-address labels, the one off-chain place such
  text plausibly lives. `uid:TRUST` saves the two hops under the labels that give
  it away. The Tell Miner now reads address-book labels **and** transaction
  remarks; mined-tell count and recall are unchanged.
- **Settlement legs are excluded from the walks, so nothing moves by construction.**
  The connectors' flow / value accessors filter to `settled_by = ''`, so every
  flow, exposure, and graph walk sees exactly the pre-redesign rows; the omnibus
  hot wallet (which has no customer in-edges) would only add plumbing. New
  withdrawal settlement legs are appended after the current max `tx_id`, so no
  existing id renumbers. Result: every exposure set, hop count, and dollar figure
  is preserved, and **all capability scorecards are byte-identical**. The single
  permitted ground-truth change is enumerated: the first betraying-tell pointer
  re-points from a transaction id to an address-book `entry_id`, gaining a
  `source_kind`. The account-name determinism canary is untouched.
- **Guarded going forward.** `tests/test_data_model_invariants.py` pins the model:
  a chain record may never carry a remark, every settlement leg links back to the
  exchange record it settles, withdrawals settle from the hot wallet, and the flow
  accessors exclude settlement legs. The determinism guards continue to cover the
  changed generator.
