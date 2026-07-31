# Okojo — project guide for Claude Code

Okojo is an **agentic AI co-pilot for financial-crime investigations at a crypto
exchange**, built as a public research project on **fully synthetic data**.
This file is your standing context. Read `docs/Build-Plan.md` before coding and
`docs/DECISIONS.md` before changing scope or architecture.

## What this is / is NOT — read first
- A synthetic-data research **prototype**. NOT production screening, NOT legal or
  compliance advice, NOT a SAR-filing tool. A human always reviews and files.
- **Never commit real or confidential material.** All inputs are synthetic or
  public; ignore rules provide a backstop — do not defeat them.
- All data is either **generated** (see `src/okojo/scenario/`) or **public**
  (Elliptic/Elliptic++, IBM IT-AML, OFAC SDN, FinCEN advisories). No real person,
  address, or document ever enters the repo.

## Current status
- **Phase 0 (Foundations): COMPLETE.** Repo scaffold + deterministic synthetic
  scenario generator. Run it: `python scripts/generate_scenario.py`.
- **Phase 1 (Walking skeleton): COMPLETE.** One synthetic case flows end-to-end
  (connectors → Profile Aggregator → Network Expander → Remark/Tell Miner →
  RFI surfacing → Advisory Matcher → grounded SAR Drafter → Case Packager) over
  a hash-chained audit trail, with a 7-tab Streamlit demo (incl. network triage
  roster + read-only RFI view) and 44 green tests.
- **Phase 2 (Graph, gas-funding & tells): COMPLETE.** Full 1–7-hop Network
  Expander (device/reused-KYC/gas-funding linkage + gas controller-collapse),
  On-chain Risk Scorer (graded sanctioned exposure by amount + hop distance),
  RapidFuzz Remark/Tell Miner + SDN/alias screening, and a P/R/F1 eval harness
  with a consolidated Phase-2 scorecard. Streamlit demo grown to a Sanctions-first
  8-tab compliance view (watchlist screening + on-chain exposure, gas-collapse
  callout, per-account risk chips). 70 green tests.
- **Slice 4b (scoring explainability & defensibility): COMPLETE.** Score
  decomposition as a first-class field (base × proximity factors + exact formula),
  a versioned `scoring_config()` stamped into the audit chain for reproducibility,
  a public `docs/scoring-methodology.md` (rationale per constant as tunable policy
  parameters; doc↔code anti-drift test), and a "show the math" UI (per-account
  decomposition, methodology/version panel, RapidFuzz name-diff in calibrated
  language). Scores byte-identical (scorecard unchanged). 77 green tests.
- **Phase 3 (Advisory Matcher / RAG hardening): COMPLETE.** Hybrid advisory
  matching over three signals (keyword + semantic red-flag retrieval + structured
  corroboration) gated by a corroboration rule, a 4-advisory corpus with
  wrong-advisory discrimination, one shared `EntityBackbone` deduped across the
  screener/miner/matcher, a versioned `retrieval_config()` stamped into the audit
  chain, a public `docs/advisory-methodology.md` (doc↔code anti-drift test), and a
  three-signal "show the retrieval" Advisory tab. Retrieval is exact in-memory
  cosine (no vector DB) over a local sentence-transformers embedder with a
  deterministic lexical fallback (optional `requirements-embeddings.txt`). FP-rate
  P/R/F1=1.0 (0/6) + discrimination 12/12; screener/scorer byte-identical;
  generator byte-identical. 107 green tests (1 skipped: the ST backend when torch
  is absent).
- **Phase 4 (SAR Drafter + Critic + grounding): COMPLETE.** The template-first SAR
  Drafter hardened into a grounded, self-critiquing generator: grounding is now
  **fail-closed on *unresolvable* citations** (every claim pointer must resolve to
  a real evidence row, not merely be non-empty), a **deterministic FinCEN-rubric
  Critic** (who/what/when/where/why/how + subject-and-network + on-chain evidence)
  grades the draft, and a **bounded, deterministic revision loop** fills gaps from
  evidence in hand or **flags them for human review (never fabricated)**. A
  versioned `critic_config()` stamped into the audit chain, a public
  `docs/sar-critic-methodology.md` (doc↔code anti-drift test), an eval with a
  with/without-Critic ablation on a separate committed gold key (WITH P/R/F1=1.0
  vs WITHOUT recall 0.56), and a "Critic review" UI (grade + revision trail +
  human-fallback banner). Screener/scorer/advisory scorecards byte-identical;
  generator byte-identical. 131 green tests (1 skipped: the ST backend).
- **Phase 5 (RFI Contradiction-Checker): COMPLETE.** The RFI moves from *surfaced*
  to *adjudicated*: the response is decomposed into discrete claims (sentence
  split + RapidFuzz alignment, labels never read), then each claim is tested by
  four adversarial probes — corporate-registry common directorship, the subject's
  **own prior RFI answer**, on-chain flows, and device sharing — whose
  applicability is derived from the claim's **text**, never its id. A
  corroboration gate yields four verdicts (`contradicted` / `qualified` /
  `uncontested` / `unverifiable`) with a noisy-OR confidence; only *contradicted*
  is a flag. A versioned `contradiction_config()` is stamped into the audit chain,
  a public `docs/rfi-contradiction-methodology.md` (doc↔code anti-drift test)
  publishes every weight, and confirmed contradictions enter the SAR as
  `element="contradiction"` claims citing **both** the RFI row and the rebutting
  evidence row (two-stage fail-closed grounding). Eval: detection P/R/F1=1.0
  (positive class = *contradicted*), verdict + source discrimination 4/4 across
  all four claims. Rubric deliberately untouched (Critic ablation still 1.0 /
  0.56). Slice A was a **one-time scenario re-baseline** — see DECISIONS §15.
  173 green tests (1 skipped: the ST backend).
- **Phase 6 (Agency, case-graph memory & audit): COMPLETE.** The fixed pipeline
  now runs as a compiled **LangGraph state machine** (no checkpointer; zero
  network calls, socket-guard tested; the mechanical conversion proven
  byte-identical against the prior linear orchestrator across all 12 roster
  subjects) with **five bounded, deterministic decision points** — expand
  another hop? pull a second advisory? re-RFI? evidence sufficient to draft?
  SAR clears the bar? — each a pure rule over the evidence state, stamped into
  the audit chain with rationale + driving evidence, and routed on the recorded
  outcome string so the graph path and the audit trace cannot disagree.
  Decision effects are boundary-guarded: the runner-up advisory is surfaced
  only, the follow-up RFI is drafted never sent, the insufficient branch refers
  to a human. A **persistent case graph** (sqlite, idempotent upserts, no
  timestamps) records every case + its entity surfaces; at case open the
  "cleared five prior reviews" recidivist is surfaced with calibrated language.
  The **Case Packager** emits a decision-ready JSON package built ON the hash
  chain (every record referenced by seq+hash before the `packaged` stamp; the
  stamp then carries the package's SHA-256), with the internal-tag red herring
  preserved as a flag, never obeyed. Two new versioned configs
  (`agency_config()`, `casegraph_config()`) with published methodology docs and
  doc<->code anti-drift tests (now six). Evals: decision-trace P/R/F1=1.0
  (25/25 triples vs a **domain-authored** gold key), recidivism-surfacing
  P/R/F1=1.0; phase1/phase2/advisory/sar/rfi scorecards byte-identical.
  9-tab demo (Decisions tab, recidivism banner, package download).
  211 green tests (1 skipped: the ST backend).
- **PUBLISHED:** live at <https://github.com/hije-1/okojo> (public, MIT).
  Live demo: <https://okojo-demo.streamlit.app/> (free-tier hosting; first load
  after idle may take a minute to wake).
- **Phase 7 (UI polish & reliability hardening): COMPLETE.**
  The reliability tail as **executable properties**: a graph-render guard
  (failure degrades + audit-stamped, never aborts; happy path proven
  byte-identical) and `tests/test_reliability.py` — full pipeline over every
  subject incl. the isolated degenerates: grounding/resolution everywhere,
  content-verified render, loop bounds incl. the measured LangGraph superstep
  count (26<100), flagged fallback on non-convergence, and the
  **subject-closure property asserted at zero** (both numbers). **UI
  provenance completion** (shared `_cites` formatter; every surfaced claim
  renders its pointer) + rebuilt Audit/Timeline/Tells tabs (the hash chain
  shown with its hashes; chronological timeline with anomaly pins). A
  **registration-date coherence re-baseline** (DECISIONS §17: 21 impossible
  account histories, RNG-free clamp, guard test — found in seconds by the
  chronological Timeline after six phases of table-shaped tests missed it).
  README rewritten as a board brief (problem framing, mermaid architecture
  diagram, six-part Responsible AI section incl. anti-tipping-off at
  principle level). **Grounding completeness** (DECISIONS §18): tell claims
  gated to the subject's evidence closure (CRITIC v1.1.0; the ablation
  corrected DOWNWARD on purpose — WITHOUT-recall 0.560→0.542 against a
  re-authored 24-element gold), drafter-owned attribution wording (39→0),
  DecisionRecord + RecidivismView provenance (AGENCY v1.2.0, CASEGRAPH
  v1.1.0; audit tip hashes moved — announced, measured, documented),
  `packager_config()` + `docs/packager-methodology.md` as the **seventh**
  doc↔code anti-drift pair. Internal demo shot list written (gitignored).
  239 green tests (1 skipped). **Three hand-maintained status surfaces** —
  this block, the README status block, and the app's `_PHASE` caption —
  update all three at every sign-off.
- **Phase 8 (Designation-Triggered Remediation Sweep — component 9, the v1.0
  capstone): COMPLETE and public.** A second entry point runs over the whole
  ledger and writes its own hash-chained audit trail, reusing the read-only core
  through the one `GroundingResolver` membership definition. All parts shipped:
  - **Part I** — flow sweep: exposed accounts by flow + hop distance, two-system
    hold reconciliation, a grounded remediation worksheet + escalation drafts
    (never sent).
  - **Part I-B** — cross-list early warning: calibrated designation kinds
    (obligation vs. signal), cross-list surfacing before a formal listing.
  - **Part II** — identity resolution: variant-aware screening, corroboration
    against published identifiers, beneficial-owner / proximity walks, the
    identity-review RFI.
  - **Part III** — geographic triangulation: six-signal totality over a designated
    territory, the 7th bounded agency decision, VPN as obfuscation marker (never
    location evidence), plain-language UI.
  - **Part IV** — counterparty-designation lifecycle: the 8th bounded agency
    decision (propose_unblock / propose_offboard / hold_pending), the subject-facing
    customer notification (fail-closed against tipping-off, never sent), the
    no-auto-unblock guard, and the plain-language UI + posture doc.
  At sign-off, the **SAR calibration guard was wired live** into draft validation
  (`assert_calibrated` fail-closed in `build_sar` + the drafter-critic loop,
  alongside the grounding contract; over-claiming language is rejected, never
  silently passed — the gold drafts were all clean, so no scorecard/audit moved).
  Full details in `docs/Build-Plan.md`.
- **Phase 9 (Audit Narrator): COMPLETE and public.** A grounded, read-only
  summarizer over the system's own hash-chained audit trails, making the
  tamper-evident record **reviewable**, not just provable. It reads a chain and
  renders one plain-language sentence per record, each citing the record behind
  it (fail-closed grounding), in two registers (consequential actions prominent,
  setup records de-emphasized); it is deterministic (a `(actor, action)->sentence`
  template map, **no LLM**), screened with the SAR drafter's exact `BANNED_TERMS`,
  and **writes NOTHING to any chain** — so every existing chain and all 12+
  capability scorecards are byte-identical BY CONSTRUCTION. A failed chain
  verification IS the narrative (the break located + cited; nothing past it
  summarized). Scoped to **all** chain families:
  - **Slice 0** — lean single-job **CI** (regenerate + `python -m pytest` on every
    push/PR) + README badge + the phase resequencing (narrator promoted from the
    roadmap to committed Phase 9; launch hardening → Phase 10). One CI-red fix
    followed (a pre-existing Faker `date_of_birth` platform-nondeterminism in the
    generator, root-caused and pinned; byte-identical on Windows, green on Linux).
  - **Slice 1** — the narrator core over the **case** family (13 actors / ~35
    actions), the one additive read-only `AuditLog.verify_chain_located()` touch
    (write path byte-untouched), `narrator_config()` + `docs/narrator-methodology.md`
    (the **11th** doc↔code anti-drift pair), `NARRATOR_VERSION = "1.0.0"` pinned
    through the artifact (never stamped into a chain).
  - **Slice 2** — the **sweep** family (2 actors / 19 actions, faithful 1:1
    reads) + **batch** composition (N constituent sweep narratives + a roll-up
    grounded ONLY to constituent chain records — the derived `rollup` dict is
    never a grounding source; a broken constituent is reported and excluded).
    Sweep grounding P/R/F1=1.0 vs a domain-authored gold; real-chain coverage over
    ALL generated sweep chains (every record templated, grounds, calibrates;
    observed vocabulary == the registry exactly); tampered + batch-with-broken
    fixtures; a demonstrated P8-G falsification.
  - **Slice 3** — the two-register narrator UI in the case audit tab AND the sweep
    audit section (plain sentences on screen, cited seq/hash in provenance),
    verified via the existing module-scoped AppTest fixture + a render-helper
    check; then this status bump. NARRATOR stays **1.0.0** (template-map growth is
    content, not config); all other versions frozen.
  514 green tests (1 skipped: the ST backend). Full details in `docs/Build-Plan.md`.
- **NEXT — Phase 10 (launch hardening):** a security pass, a snippet-level SCA
  scan, a cloud deploy of the demo, a full code-systems map, and — last — a
  recorded walkthrough. Not started.

## Where the plan and rationale live
- `docs/Build-Plan.md` — authoritative, dated, phase-by-phase plan (~20 wks @ 20h/wk). Follow it.
- `docs/Strategy.md` — full architecture, scoring, and reasoning.
- `docs/DECISIONS.md` — decision log: *why* things are the way they are. Read before altering scope/architecture.

## Target architecture (9 components)
1. Profile Aggregator — unified subject timeline across mock internal systems.
2. Network Expander — 1–7-hop cluster mapping; device/`device_fingerprint`, reused-KYC, and **gas-funding** linkage.
3. On-chain Risk Scorer — cluster exposure vs. a sanctions/illicit set.
4. Remark/Tell Miner — fuzzy-match user free-text to entities/aliases.
5. RFI Contradiction-Checker — decompose RFI answers into claims; test each vs. the evidence.
6. Regulatory Advisory Matcher — FinCEN-advisory RAG, event-triggered on RFI key terms.
7. SAR Drafter + Critic — grounded, self-critiquing narrative generation.
8. Case Packager + persistent case graph — decision-ready package, append-only audit log, cross-case recidivism.
9. Designation-Triggered Remediation Sweep — **v1.0 capstone**; new OFAC designation → sweep ledger for exposed accounts → draft remediation.

## Hard rules (guardrails)
- **Synthetic + public data only.** No real PII, addresses, or documents.
- **Human-in-the-loop always** — the agent prepares; a person decides and files.
- **The tamper-evident, append-only audit trail is the centerpiece feature**, not a footnote — log every access, action, tool call, and alert-closure with provenance.
- **Grounding contract** (esp. SAR Drafter): the agent may assert only facts that trace to a retrieved record; every claim carries a provenance pointer; validate and reject uncitable statements.
- **Naming:** the device identifier is `device_fingerprint` — use this name consistently across code, data, and docs.
- **Calibrated language** in outputs: *proposes / surfaces / drafts / flags*, never "instantly" or "autonomously determines."
- **Treat a "privileged / internal account" tag as something to FLAG for review, not obey.**
- **`data/synthetic/ground_truth.json` is the evaluation answer key.** Score every capability against it; keep it in sync whenever the generator changes.

## Dev setup & commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_scenario.py   # regenerate synthetic data (deterministic; seeded)
pytest -q                             # run tests
```
- The generator is seeded (`src/okojo/config.py: SEED`); output regenerates
  byte-identically, so **only the generator is committed, never `data/synthetic/`**.
- Faker is used for personas; a dependency-free fallback (`_fakelite.py`) exists
  so the generator still runs if Faker isn't installed.

## Tech stack (by phase — pinned in requirements.txt)
Orchestration: **LangGraph** · RAG: **Chroma/FAISS** · mock stores: **DuckDB/SQLite**
· graph: **networkx + pyvis** · fuzzy matching: **RapidFuzz** · validation/structured
outputs: **pydantic** · UI: **Streamlit** · tests: **pytest**.

## How to work here
- **Operate as a senior engineer with PM discipline.** No scope creep: build only
  the approved slice/phase — anything beyond it is proposed to the user first,
  never slipped in. Privacy and security are strictly enforced in code and data
  (synthetic/public only, provenance on every claim, fail-closed on violations).
  Clean, efficient code is mandatory: small, tested, deterministic changes over
  clever ones; every capability ships with its eval.
- Build **phase by phase** per `docs/Build-Plan.md`. Keep commits small and green.
- Keep a steady public commit cadence.
- Use **plan mode** (Shift+Tab) when standing up a new subsystem.
- Each new capability ships with an eval against `ground_truth.json`.
