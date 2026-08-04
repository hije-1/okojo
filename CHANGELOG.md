# Changelog

All notable changes to Okojo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Okojo is a synthetic-data research prototype — an agentic AI co-pilot for
financial-crime investigations at a crypto exchange. It is not production
screening, not legal or compliance advice, and not a SAR-filing tool; a human
always reviews, decides, and files. All data is synthetic or public.

## [Unreleased]

### Added
- **Screening coverage-gap check (institution-level).** A read-only assessment
  that measures the customer base's whole geographic footprint against the
  enabled list-source regimes and surfaces the mismatch as a standing, cited
  finding — the automated form of a coverage argument practitioners otherwise
  make by hand.
  - The footprint is three separately-counted, separately-cited legs — residence
    country, KYC-issuing country, and nationality (the nationality leg surfaces a
    no-coverage jurisdiction the residence leg alone would miss).
  - Two gap classes: an *ingestion gap* (a jurisdiction covered only by a
    declared-but-not-ingested regime) and a *no-coverage gap* (covered by no
    regime at all). Both are calibrated as a screening-scope observation, not a
    legal claim.
  - A new versioned `coverage_config` (the regime → jurisdiction coverage policy)
    with its own methodology doc and doc↔code anti-drift guard — the twelfth such
    pair. The frozen sweep list-source registry is read, never duplicated, so
    what counts as *enabled* coverage can never drift from the sweep.
  - Its own hash-chained audit trail (a new `coverage` chain family under
    `data/coverage/`), narrated by the read-only Audit Narrator (five new
    templates; the narrator remains v1.0.0 — additive template growth).
  - A "Screening coverage" panel in Designation-sweep mode, with a one-line
    pointer from the case Sanctions tab.
- Scored against `ground_truth.json` (exact-set footprint / covered / gap
  membership, plus a falsification that flips a regime's ingested status). All
  existing capability scorecards are byte-identical; no version but `coverage`
  moved.

## [1.1.0] - 2026-08-03

### Added
- **Subject-as-seed designation check on the case pipeline.** A read-only check
  runs on the unconditional case backbone (right after risk scoring): it screens
  each case subject and its expansion cluster against the designation lists and
  surfaces the posture on the Sanctions tab.
  - A three-state posture badge — corroborated designation match / active or
    name-only hit / no match — with a cited, always-visible dismissal line for a
    name-only hit.
  - Fund-flow and hop-distance exposure lines, a designated-territory line, and
    named-network notices for cluster-level hits (cluster hits never escalate the
    subject's own badge).
  - A ledger-wide screening-coverage footer (designations screened, list sources,
    and any list that is visibly absent).
  - One unconditional `designation_check/screened` proof-of-screening record per
    case, embedding the corroboration outcome and any mismatched fields.

### Changed
- **License changed to the Business Source License 1.1** for v1.1.0 and later:
  source-available; non-production use (research, evaluation, demonstration) is
  free, production or commercial use requires a license from the Licensor, and
  each version converts to the MIT License on its Change Date (2030-08-03).
  Versions **v1.0.0 and earlier remain under the MIT License**.
- **Case-UI polish.** The case tabs render in component order (the subject's
  Timeline first); on-chain risk-score reason codes and score-decomposition kinds
  render in plain language; the case Sanctions tab carries a scope caption; and
  the case Tells tab header reads "Tells."
- A ™ mark on the prominent use of the Okojo name (README title, app header, and
  browser tab title).

### Notes
- No capability version was bumped and no new ground-truth keys were added — all
  capability scorecards are byte-identical to v1.0.0. By design, each case audit
  chain gains the one new proof-of-screening record.

## [1.0.0] - 2026-07-31

First public release. Okojo runs a synthetic case end-to-end — profile
aggregation, network expansion, on-chain risk scoring, tell mining, RFI
contradiction-checking, advisory matching, grounded SAR drafting, and case
packaging — over a tamper-evident, hash-chained audit trail, with a
designation-triggered remediation sweep as the capstone and a grounded Audit
Narrator that makes the audit trail reviewable. Built phase by phase; every
capability ships with an eval against a committed synthetic answer key.

### Phase 0 — Foundations
- Repository scaffold and a deterministic, seeded synthetic scenario generator
  (`scripts/generate_scenario.py`). Only the generator is committed — the
  dataset regenerates byte-identically from the seed.

### Phase 1 — Walking skeleton
- One synthetic case flows end-to-end (connectors → Profile Aggregator →
  Network Expander → Remark/Tell Miner → RFI surfacing → Advisory Matcher →
  grounded SAR Drafter → Case Packager) over a hash-chained audit trail, with a
  Streamlit demo.

### Phase 2 — Graph, gas-funding, and tells
- Full 1–7-hop Network Expander (device / reused-KYC / gas-funding linkage and
  gas controller-collapse), an on-chain Risk Scorer that grades sanctioned
  exposure by amount and hop distance, a RapidFuzz Remark/Tell Miner with
  SDN/alias screening, and a precision/recall/F1 eval harness.
- Scoring explainability (Slice 4b): score decomposition as a first-class field,
  a versioned scoring config stamped into the audit chain, and a public scoring
  methodology doc with a doc↔code anti-drift test.

### Phase 3 — Advisory Matcher / RAG hardening
- Hybrid advisory matching over keyword and semantic red-flag retrieval plus
  structured corroboration, gated by a corroboration rule, with a shared
  deduplicated entity backbone, a versioned retrieval config, and a public
  advisory methodology doc. Retrieval is exact in-memory cosine over a local
  embedder with a deterministic lexical fallback (no vector database).

### Phase 4 — SAR Drafter and Critic
- A template-first, grounded SAR Drafter that fails closed on unresolvable
  citations; a deterministic FinCEN-rubric Critic; and a bounded revision loop
  that fills gaps from evidence in hand or flags them for human review (never
  fabricated). Versioned critic config and a public critic methodology doc.

### Phase 5 — RFI Contradiction-Checker
- RFI responses are decomposed into discrete claims and tested by adversarial
  probes (common directorship, the subject's own prior answers, on-chain flows,
  device sharing). A corroboration gate yields four verdicts, and confirmed
  contradictions enter the SAR citing both the RFI row and the rebutting evidence
  row. Versioned contradiction config and methodology doc.

### Phase 6 — Agency, case-graph memory, and audit
- The fixed pipeline runs as a compiled LangGraph state machine with five
  bounded, deterministic decision points, each stamped into the audit chain with
  its rationale and driving evidence. A persistent case graph surfaces cross-case
  recidivism at case open, and the Case Packager emits a decision-ready package
  built on the hash chain. Versioned agency and case-graph configs with
  methodology docs.

### Phase 7 — UI polish and reliability hardening
- Reliability properties as executable tests (graph-render guard that degrades
  rather than aborts, loop bounds, subject-closure), UI provenance completion
  (every surfaced claim renders its citation), grounding completeness (tell
  claims gated to the subject's evidence closure), and a board-brief README with
  an architecture diagram. Versioned packager config and methodology doc.

### Phase 8 — Designation-triggered remediation sweep (v1.0 capstone)
- A second entry point runs over the whole ledger with its own hash-chained
  audit trail: a flow-based exposure sweep with a remediation worksheet,
  cross-list early warning, variant-aware identity resolution, geographic
  triangulation, and a counterparty-designation lifecycle — all human-in-the-loop
  (escalations and customer notifications are drafted, never sent).
- The SAR calibration guard was wired live into draft validation, so
  over-claiming language is rejected rather than silently passed.

### Phase 9 — Audit Narrator
- A grounded, read-only summarizer over the system's hash-chained audit trails
  that renders one cited, plain-language sentence per record, in two registers,
  across the case, sweep, and batch chain families. Deterministic (a template
  map, no LLM); a failed chain verification is itself the narrative — the break
  is located and cited, and nothing past it is summarized. The narrator writes
  nothing to any chain, so every existing chain and scorecard is byte-identical.
  Versioned narrator config and methodology doc.

### Phase 10 — Launch hardening
- Continuous integration (regenerate plus the full test suite on every push and
  pull request) with a status badge; a security pass (dependency and
  static-analysis scanning with documented triage); a Tier-2 software-composition
  -analysis scan before release; a full code-systems map with a completeness
  tripwire test; a boot-time data-regeneration hook; and a cloud-hosted live
  demo.

[1.0.0]: https://github.com/hije-1/okojo/releases/tag/v1.0.0
