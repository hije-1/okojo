# Decision Log & Context Transfer

This file preserves the reasoning behind Okojo so that anyone (or any agent)
picking up the project has the full context that would otherwise live only in a
chat history. Read it before changing scope, architecture, or the data model.
Companion docs: `Strategy.md` (full write-up) and `Build-Plan.md` (dated plan).

_Last updated at handoff from the planning phase (Phase 0 complete)._

---

## 1. Goal & audience
A public GitHub portfolio project for a **senior crypto-compliance executive who
is AI-forward**. It must read as sophisticated to a compliance hiring manager
*and* show genuine hands-on agentic-AI engineering ("balance of both"). Built
from scratch, solo, ~20 hrs/week.

## 2. Scope decision — one flagship, not a suite
A single, deliberately-scoped flagship with a documented roadmap beats a
scattered set of demos: for a senior audience, choosing what to build and what to
defer *is* the signal. The flagship is an **agentic crypto-investigations
co-pilot** ("Okojo") that fuses several top pain points under one narrative.

## 3. How capabilities were chosen
Ten candidate pain points were scored 1–5 on six dimensions: **Data** (buildable
with public/synthetic data), **Build** (solo-feasible), **Agentic** (real
tool-use/reasoning, not a classifier), **Domain** (compliance/FIU sophistication),
**Safe** (publishable — no PII/opsec/reputational hazard), **Wow**
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
- **Roadmap (post-v1.0, ordered by payoff):** the **Audit Narrator** (grounded
  summarizer over Okojo's own hash-chained audit log — makes the tamper-evident
  trail *reviewable*, not just provable; low marginal cost, reuses the native log)
  first; then PP-13 (ML auto-closure QA) and #8 (vendor reconciliation); then PP-14
  (tokenized-commodity tracing — kept out of v1.0 despite timeliness because it
  needs new contract-tracing tooling with little reuse), #5 (multilingual OSINT),
  #4/#7 (LE-request/MLAT routing). Build these in public after launch to keep the
  repo visibly growing. (See §13.)

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
- Set up the public GitHub repo + a steady commit cadence (the public history is
  itself a portfolio signal).

## 12. Licensing & contribution policy
_Added Day 3 (Phase 2 complete)._

- **MIT retained through the portfolio phase — deliberate.** It maximizes the
  repo's job-search value and costs nothing long-term: the author remains the sole
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

## 13. Audit Narrator added to the roadmap (post-v1.0)
_Added Day 3 (Phase 2 + Slice 4b complete)._

- **Audit Narrator added to the roadmap (user-proposed).** Prioritized *ahead of
  PP-13* because it reuses Okojo's native hash-chained audit log — no new data and
  no new privacy surface — and directly strengthens the audit-trail centerpiece:
  it makes a *provable* log *reviewable*. A grounded summarizer over the log emits
  (a) a plain-language, citation-backed case narrative and (b) an actor/pattern
  access review that flags unusual access for human review.
- **Guardrails carry over unchanged:** the grounding contract and calibrated
  language apply — every summary sentence cites the log entries behind it, and
  anomalies are *flagged for human review, never concluded*.
- **Deliberately not built now — roadmap discipline holds.** Logged here as scope;
  build order stays per `docs/Build-Plan.md`. Candidate to pull into v1.0 only if
  schedule cushion allows.

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
- **Sole-authorship posture (preserved).** MIT-licensed for the portfolio phase,
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
