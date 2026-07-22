<p align="center">
  <img src="okojo-logo.png" alt="Okojo logo" width="180">
</p>

# Okojo — an Agentic Crypto-Investigations Co-Pilot

> **Status:** Phase 1 — walking skeleton. One synthetic case now flows end-to-end
> through a thin version of every stage (profile → network → tells → RFI →
> advisory → grounded SAR), over a tamper-evident audit trail, with a minimal Streamlit demo.
> This repository is being built in the open as a portfolio project; the remaining
> capabilities land phase by phase (see the roadmap).

Okojo is a research prototype of an **agentic AI co-pilot for financial-crime
investigations at a crypto exchange**. In the full v1.0 design, given a flagged
account, it assembles a unified subject profile, expands the account into its
on-chain entity cluster, mines user-generated tells, checks a subject's
request-for-information (RFI) answers against the evidence, grounds its findings
in the relevant FinCEN advisories, and drafts an intelligence-rich Suspicious
Activity Report — handing a human a decision-ready package with a complete,
tamper-evident audit trail. (Phase 1 surfaces the RFI read-only; claim-by-claim
contradiction checking lands in Phase 5.)

---

## ⚠️ What this is — and what it is NOT

**What this is:** a demonstration, on **fully synthetic data**, of how agentic AI
can support (never replace) a human investigator in a regulated workflow.

**What this is NOT:**

- **Not** a production screening or transaction-monitoring system.
- **Not** legal, compliance, or sanctions advice.
- **Not** a SAR-filing tool — a human reviews, decides, and files. SARs carry
  strict confidentiality obligations; nothing here should be construed as, or
  used for, an actual regulatory filing.
- **Not** built on, and does **not** contain, any real customer data, real
  identities, real wallet addresses, or real documents. Every person, company,
  address, device, and transaction is fabricated by the generator in
  `src/okojo/scenario/`.

The scenario **replicates behavioural patterns** documented in public reporting
and sanctions actions (shell-entity rings, reused KYC documents, structured
transfers, false RFI narratives) so the co-pilot has realistic material to reason
over. Patterns are not people.

---

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# generate the synthetic oil / sanctions-evasion scenario
python scripts/generate_scenario.py

# run the tests
pytest -q

# launch the walking-skeleton demo (pick a subject, watch the case flow end-to-end)
streamlit run app/streamlit_app.py
```

Output is written to `data/synthetic/` (git-ignored). Because generation is
fully deterministic (seeded), the dataset regenerates identically — so only the
generator is committed, never the data.

### The walking skeleton (Phase 1)

Given a flagged subject, the thin orchestrator runs the mock connectors →
Profile Aggregator (anomaly-flagged timeline) → Network Expander (subject-seeded
graph) → Remark/Tell Miner → FinCEN Advisory Matcher → grounded SAR
drafter → Case Packager, logging every step to an append-only, hash-chained
audit trail. Every asserted fact carries a provenance pointer; the SAR drafter
fails closed on any uncitable claim.

### What the generator plants

A cross-border ring with an ultimate controller hiding behind family- and
employee-cutout directors, plus the tells a good investigator looks for — each
also recorded in `ground_truth.json` as an answer key for scoring:

| Pattern | Where it shows up |
|---|---|
| Reused KYC document across "separate" entities | `kyc_docs.csv`, `accounts.csv` |
| Shared devices (`device_fingerprint`) across unrelated accounts | `devices.csv` |
| Logins from a sanctioned jurisdiction interleaved with VPN | `ip_logs.csv` |
| Structured just-under round-number transfers | `transactions.csv` |
| Gas-funding that betrays control of a "non-custodial" wallet | `gas_funding.csv` |
| Withdrawal remarks naming the true controller | `transactions.csv` |
| A licensed-trust RFI narrative contradicted by the evidence | `rfi.csv` + `ground_truth.json` |
| A recidivist account that cleared prior "retain & monitor" reviews | `accounts.csv` |
| An "internal account, do-not-block" red-herring tag | `accounts.csv` |

---

## Architecture (target)

A supervisor/orchestrator over specialized tools, built as an explicit,
inspectable state machine (legibility is a compliance feature):

1. **Profile Aggregator** — unified subject timeline across mock internal systems.
2. **Network Expander** — 1–7-hop cluster mapping with device/`device_fingerprint`, reused-KYC, and **gas-funding** linkage.
3. **On-chain Risk Scorer** — cluster exposure against a sanctions/illicit set.
4. **Remark/Tell Miner** — fuzzy-matches user free-text to entities/aliases.
5. **RFI Contradiction-Checker** — decomposes RFI answers into claims and tests each against the evidence.
6. **Regulatory Advisory Matcher** — FinCEN-advisory RAG, event-triggered on RFI key terms.
7. **SAR Drafter + Critic** — grounded, self-critiquing narrative generation.
8. **Case Packager + persistent case graph** — decision-ready package, append-only audit log, cross-case recidivism.
9. **Designation-Triggered Remediation Sweep** *(v1.0 capstone)* — given a new OFAC designation, sweep the full ledger for exposed accounts and draft remediation.

**Roadmap (post-v1.0):** ML alert auto-closure QA · vendor reconciliation ·
tokenized-commodity issuance tracing · multilingual OSINT verifier · LE-request/MLAT routing.

---

## Responsible AI & tamper-evident audit trail

The design principle that matters most here: **the audit trail is a feature, not
a footnote.** Every access, tool call, agent decision, and alert-closure is
logged, append-only, with provenance — and the agent's factual claims are
grounded, meaning it may only assert what traces to a retrieved record. A
"privileged / internal account" tag is treated as something to **flag for
review, not obey.** Human-in-the-loop throughout: the agent prepares; a person
decides and files.

## Author

Built by **Jennifer Hicks**, a crypto-compliance leader exploring agentic AI for
regulated financial-crime investigations. Connect on
[LinkedIn](https://www.linkedin.com/in/hije/).

## License

MIT — see [LICENSE](LICENSE).
