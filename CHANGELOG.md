# Changelog

All notable changes to Okojo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Okojo is a synthetic-data research prototype — an agentic AI co-pilot for
financial-crime investigations at a crypto exchange. It is not production
screening, not legal or compliance advice, and not a SAR-filing tool; a human
always reviews, decides, and files. All data is synthetic or public.

## [1.1.2] - 2026-08-13

This release remediates the findings of an external, third-party code audit. An
independent auditor — ChatGPT Codex, operated under a written, read-only audit
brief — ran an adversarial review of Okojo's code quality, correctness, and
security at v1.1.1. Seven findings (five medium, two low) were triaged, accepted,
and fixed, each with regression tests. No public API contract changed and all
deterministic capability scorecards remain byte-identical.

> **[Correction, 2026-08-17]** "No public API contract changed" is wrong. This
> release *did* change a public contract: the answer-key removal below also
> removed `ground_truth` and `contradicted_by` from the public `RfiClaim` model
> and from the `CaseResult.rfi` shape. See [1.1.3] for the migration note. The
> scorecard byte-identity claim is unaffected.

### Security
- **Bounded designation-name variant expansion.** The advanced designation input
  now caps designated-name length and token count at the validation boundary and
  enforces a hard variant-expansion budget before the romanization Cartesian
  product is enumerated, so an oversized paste is a clean rejection rather than an
  unbounded expansion.

### Fixed
- **Runtime RFI records no longer carry the scenario answer key.** The RFI view
  returned at runtime no longer exposes per-claim ground-truth labels or authored
  rebuttal notes; evaluation reads those only from the answer-key files. The
  generator and its outputs are unchanged.
- **Coverage assessment consumes its published configuration.** The
  institution-level coverage assessment now builds its footprint legs by
  iterating the versioned footprint configuration instead of a hard-coded list,
  so a configuration edit drives runtime behavior. Default output is unchanged.
- **Boundary-aware territory/IP matching.** Territory matching over free-text IP
  geolocation (the ordinary and VPN-slip paths) now uses tokenized,
  boundary-aware matching instead of raw substring containment, so a code or
  place token embedded inside a longer word no longer produces a false location
  signal.
- **Honest bootstrap regeneration.** When the synthetic dataset is incomplete,
  the boot-time hook now generates into a temporary sibling directory and swaps
  the complete dataset in atomically; a failed regeneration leaves the existing
  dataset intact. The documentation now states that an incomplete dataset is
  replaced wholesale (no per-file preservation).
  **[Correction, 2026-08-17]** "atomically" overstated it — the swap is two
  sequential renames with a brief window in which the target path is absent.
  See [1.1.3].
- **Single version source.** `okojo.__version__` now derives from the installed
  package metadata (with a source-tree fallback) instead of a stale literal, so
  the importable version matches the distribution version.

### Changed
- **Pinned GitHub Actions and least-privilege workflows.** The CI and security
  workflows pin `actions/checkout` and `actions/setup-python` to full commit SHAs
  (the version tag retained in a comment) and declare a workflow-level
  `permissions: contents: read`.

[1.1.2]: https://github.com/hije-1/okojo/releases/tag/v1.1.2

## [1.1.1] - 2026-08-11

### Added
- **Packaging (`pyproject.toml`).** Okojo is now pip-installable from a source
  checkout under its existing `src/` layout, so downstream projects can declare
  it as a git-pinned dependency. Packaging only — **zero behavior change**:
  runtime pins mirror `requirements.txt` exactly, `pytest` is exposed as a `dev`
  extra, and the advisory RAG corpus (`src/okojo/advisory/corpus/*.md`) is
  declared as package data so it ships in the installed distribution. No source
  or test files changed; all capability scorecards byte-identical; the
  account-name determinism canary untouched.

## [1.1.0] - 2026-08-03

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
- **Reviewer disposition on the case audit chain.** A human reviewer's decision
  on the finished case package — *Approve* or *Review Needed*, with a required
  written rationale — is written *into* the same tamper-evident hash chain as the
  agent's work, so the record carries not just what the agent prepared but what
  the person decided.
  - A new audit record type (actor `human_reviewer`, action `reviewer_disposition`)
    built by a pure, disk-free `build_reviewer_disposition_record`; recorded and
    surfaced only — it re-runs nothing and changes no case state.
  - On the public demo the decision appends to a session-local copy of the chain
    that re-verifies and re-narrates live, while the canonical data on disk is
    never written; with no decision recorded the surface is byte-identical to the
    canonical chain.
  - Narrated by the read-only Audit Narrator (one additive template; the narrator
    remains v1.0.0), and surfaced in a "Reviewer decision" panel at the foot of
    the case Audit-trail tab (both buttons disabled until a rationale is entered).
  - Verified by invariant, not a gold key (a human decision has no predetermined
    correct answer): required rationale, session-chain re-verification,
    canonical-bytes byte-identity, a grounded + calibrated narrator line, and a
    demonstrated falsification. Deferred as out of v1 scope: approve-with-changes,
    sweep-side dispositions, timeout/default-to-hold, reviewer-authority tiers.
- **Guided walkthrough — a narrative tour over both modes.** A sidebar toggle
  (on by default) shows a fixed narrative band above each mode's tab bar and at
  the top of every tab, walking a first-time reviewer through what each surface
  shows and why. The only behaviour it adds is the toggle: no computed value,
  pipeline call, audit write, or data read happens in a walkthrough band, and
  with the toggle off the app is its pre-walkthrough self. The narrative text is
  asserted verbatim in the tests, so it cannot silently drift.

### Changed
- **Designation-sweep mode split into six investigator-flow tabs** (Triage,
  Identity, Geo, Counterparty, Coverage, Audit) — a display relocation only:
  every section moved verbatim into its tab, each still computing over the same
  sweep result.
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
- **Plain-language reviewer narrative (SAR drafts + timeline anomalies).** An
  across-the-board tightening so an investigator never has to infer who a bare
  account id is or decode jargon. Shared-device / reused-KYC anomalies and the
  SAR tell / how / contradiction claims now name each party outright (`uid N
  (Name)`); the previously unnamed gas funder is named from the address table;
  name-match and address-book tells read as plain sentences with the miner's
  internal tag jargon stripped; jurisdiction codes expand on first use (`Iran
  (IR)`) via a new `config.jurisdiction_label` (invented geo codes deliberately
  have no entry and never render as a real place); and several labels are
  de-jargoned (`High severity —`, `combined confidence`, `N finding(s) across M
  independent source type(s)`). Wording and attribution only — no generator,
  scores, audit, or config moved; every claim still cites only rows inside the
  subject's evidence closure, and the grounding and calibration contracts hold.

### Fixed
- **Early-warning Triage gap — a corroborated variant hit reaches the worksheet.**
  A corroborated transliteration-variant identity hit on a foreign early-warning
  signal list previously surfaced only in the sweep's Identity view, never in the
  Triage worksheet a reviewer works first. Name and variant identity hits now
  share one worksheet, variant rows corroboration-gated: a corroborated hit or a
  held possible-match hit surfaces (the latter marked for human review), while a
  dismissed same-name collision — a resolved false positive — never becomes a
  remediation row. A foreign early-warning designation also carries a Triage
  notice that names the specific list source and frames every finding as a risk
  signal for human review, not a binding obligation. The fix carries its own
  worksheet-coverage answer key and a demonstrated falsification; it reuses the
  existing action vocabulary, so no config, version, or unrelated scorecard moved
  (the intended DES-0005 / DES-0006 worksheet delta is the only behavioral change).
- **Two-record transaction data model — the memo-on-chain realism flaw.** The
  prior one-row model let a single on-chain transfer also carry a customer's
  free-text remark, which a real chain transfer (address → address, no memo
  field) cannot. Each value movement is now split into the exchange's internal
  record (a customer-attributed `uid:` leg, which may carry a remark) and the
  on-chain transaction (address → address, never a remark), tied by a
  `record_kind` discriminator and settlement links. Customer withdrawals settle
  on-chain from a single omnibus hot wallet, never a customer address; these
  settlement legs are excluded from the flow / value / graph walks, so every
  exposure set and dollar figure is preserved by construction. Customer free text
  moves to its realistic home — a new customer address-book table of saved
  withdrawal-address labels — which the Tell Miner now reads alongside
  transaction remarks (tell recall unchanged). A one-row relabel was proven to
  sever the exposure path (the exposed set collapsed 8 → 3) and was rejected
  under stop-on-drift; the chosen model is byte-identical across every capability
  scorecard, with a single enumerated ground-truth change (one betraying-tell
  pointer re-points from a transaction to its address-book entry). The
  account-name determinism canary is untouched.
- **Gas-funding rendered at the address level (network-graph realism).** The
  network graph collapsed the gas-funding inference onto the subject's
  exchange-account node — drawing edges from the account to the funded
  "non-custodial" wallets, which is impossible: gas is paid at the address level
  in native coin, and an off-chain custodial account cannot pay on-chain gas for
  a self-hosted wallet. The graph now renders the inference as three cited
  steps — the account *controls* the funder wallet (attribution), and the funder
  wallet *tops up* the funded wallets' gas (an observed native-coin TRX
  transfer) — with the account never sourcing an on-chain edge and the
  attribution edge visually distinct from the gas observation. Render-only: the
  underlying data was already address → address, so every network metric,
  exposure set, and capability scorecard is byte-identical, and the account-name
  determinism canary is untouched.

### Notes
- The additions after the v1.1.0 tag ride on the release without a new tag. The
  only new capability version is `coverage_config` (COVERAGE 1.0.0, for the
  coverage-gap check); every other capability version is frozen, and all
  pre-existing capability scorecards remain byte-identical (the only intended
  scored deltas are the additive designation-check and Triage variant-worksheet
  gold keys). Ground-truth changes are additive keys plus one enumerated pointer
  re-target (the two-record data model); the account-name determinism canary is
  untouched throughout. By design, each case audit chain gains the one
  proof-of-screening record, and a recorded reviewer disposition appends only to
  the demo's session-local chain copy (the canonical on-disk chain is unchanged).

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
