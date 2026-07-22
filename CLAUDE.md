# Okojo — project guide for Claude Code

Okojo is an **agentic AI co-pilot for financial-crime investigations at a crypto
exchange**, built as a public portfolio project on **fully synthetic data**.
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
- **NEXT: publish the walking skeleton to GitHub, then Phase 2** (full network
  expansion, gas-funding linkage, fuzzy tell matching, eval metrics).
  Full details in `docs/Build-Plan.md`.

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
- Build **phase by phase** per `docs/Build-Plan.md`. Keep commits small and green.
- Publish the Phase 1 walking skeleton early (it's the first shareable artifact).
- Use **plan mode** (Shift+Tab) when standing up a new subsystem.
- Each new capability ships with an eval against `ground_truth.json`.
