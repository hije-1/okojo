# Building an Agentic AI Portfolio Project: Strategy & Viability Analysis

**Prepared for:** Jennifer Hicks, CAMS-RM, CGSS, PMP
**Purpose:** Identify which of your 10 documented investigation pain points is the most viable foundation for a from-scratch agentic AI demo — one that lives on GitHub and positions you as an AI-forward senior compliance leader.
**Date:** July 21, 2026

---

## 1. How I evaluated the ten pain points

For a *public portfolio* piece built *from scratch* — with no access to production exchange infrastructure, real customer data, or proprietary vendor APIs — the constraints are different from a production build. A pain point is "viable" here only if you can build something credible with synthetic or public data, ship it solo in a matter of weekends, make it genuinely *agentic* (not just a classifier or a script), and have it read as sophisticated to a compliance hiring manager *and* safe to publish openly.

I scored each pain point 1–5 on six dimensions:

- **Data** — Can it be built with public or synthetic data, with no proprietary access?
- **Build** — Is it realistically buildable solo in a bounded timeframe?
- **Agentic** — Does it showcase real agent behavior (planning, tool use, multi-step orchestration, self-critique) rather than a single model call?
- **Domain** — Does the problem signal deep compliance/FIU sophistication to an expert reviewer?
- **Safe** — Is it clean to publish on a public repo (no real PII, no operational-security or reputational hazard)?
- **Wow** — Is it visually or conceptually distinctive — does it stand out in a portfolio and lean on *your* differentiators?

## 2. Scored ranking (all 10)

| # | Pain point | Data | Build | Agentic | Domain | Safe | Wow | **Total /30** |
|---|-----------|:----:|:-----:|:-------:|:------:|:----:|:---:|:-------------:|
| 2 | Network & cluster mapping | 5 | 3 | 5 | 5 | 5 | 5 | **28** |
| 3 | "Defensive" SAR / high-quality SAR drafting | 5 | 5 | 4 | 5 | 5 | 4 | **28** |
| 1 | Fragmented data silos → unified subject timeline | 5 | 4 | 4 | 5 | 5 | 3 | **26** |
| 5 | Multilingual document + OSINT verification | 4 | 4 | 5 | 4 | 4 | 5 | **26** |
| 4 | Triaging law-enforcement requests (RFI/MLAT intake) | 4 | 4 | 4 | 4 | 5 | 3 | **24** |
| 8 | Reconciling conflicting blockchain-analytics vendors | 3 | 3 | 5 | 5 | 4 | 4 | **24** |
| 7 | Cross-border legal routing / MLAT determination | 4 | 4 | 3 | 4 | 5 | 3 | **23** |
| 9 | Conflicting law-enforcement seizure requests | 4 | 3 | 3 | 3 | 5 | 3 | **21** |
| 6 | Data-integrity / system reconciliation | 4 | 3 | 2 | 3 | 5 | 2 | **19** |
| 10 | Privileged / VIP account roadblocks | 4 | 3 | 2 | 3 | 2 | 2 | **16** |

### What the scores tell us

**The top tier (#2, #3, #1, #5)** clusters tightly, and not by accident — each is data-rich (public datasets exist), LLM- or graph-native, and central to the daily investigator experience that a compliance leader will instantly recognize.

**The bottom tier is bottom for real reasons.** #6 (data reconciliation) is genuinely important operationally but is essentially a diffing script — hard to make *agentic* and unglamorous in a portfolio. #10 (VIP roadblocks) is the one I'd actively steer you *away from*: an open-source project whose headline is "AI that routes around controls protecting privileged accounts" reads badly out of context, regardless of how carefully you frame the tiered-access logic. Keep that insight for an interview conversation, not a public repo.

**Two mid-tier entries punch above their rank for you specifically.** #8 (vendor reconciliation) and #5 (multilingual OSINT) both map onto rare parts of your background — your Chainalysis/Elliptic on-chain lineage and your Mandarin-linguist / OSINT tradecraft respectively. They score lower only because #8 is data-access constrained (you'd be simulating "multiple vendors" rather than calling real ones) and #5 carries mild care-in-publishing overhead. Both are excellent *modules* or *second projects*.

**Update after a typology deep-dive.** Pressure-testing the field against publicly documented Iranian-oil / "shadow-banking" typologies (FinCEN advisories, OFAC designations, published exchange enforcement actions) re-ranked it: two capabilities buried inside the original ten are what actually crack attribution in documented investigations, and three genuinely new pain points emerged. Scored on the same six dimensions:

| Pain point | Data | Build | Agentic | Domain | Safe | Wow | **/30** |
|-----------|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| RFI contradiction-checking (promoted from #5) | 5 | 3 | 5 | 5 | 5 | 5 | **28** |
| Remark / tell mining (PP-11) | 5 | 4 | 4 | 5 | 5 | 5 | **28** |
| Designation-triggered remediation sweep (PP-12) | 5 | 4 | 4 | 5 | 5 | 4 | **27** |
| ML alert auto-closure QA (PP-13) | 4 | 4 | 4 | 4 | 4 | 4 | **24** |
| Tokenized-commodity issuance tracing (PP-14) | 3 | 2 | 4 | 5 | 4 | 5 | **23** |

The first two are folded into the flagship's headline capabilities below; **PP-12 is promoted to a committed v1.0 capstone** (see the MVP / capstone / roadmap split); PP-13 and PP-14 remain roadmap, re-ordered by payoff.

## 3. Scope recommendation: one flagship, not a suite

You asked me to weigh this. **Build one flagship project, deliberately scoped, with a documented roadmap — not a scattered suite of small demos.**

Here's the reasoning. You are not applying for a junior ML-engineer role where breadth-of-tricks matters; you are a senior compliance executive proving you can *architect* agentic systems and reason about them at a systems level. One coherent, well-scoped project demonstrates exactly the judgment that seniority is about: choosing what to build, what to defer, and why. Three thin demos demonstrate the opposite — that you optimized for surface area. A single flagship with a clearly-articulated MVP boundary and a "future work" roadmap actually *shows off* product-scoping discipline, which is itself a senior signal.

The elegant move is that a single flagship can *contain* several of your top-ranked pain points as distinct agent capabilities under one narrative. That's the recommendation below.

## 4. Primary recommendation — the flagship

### "Okojo" — an Agentic Crypto-Investigations Co-Pilot
*(name it whatever you like; a codename just makes the repo feel like a product)*

**The narrative.** A single flagged account arrives in the queue. Instead of an investigator spending hours clicking across a dozen dashboards, an orchestrating agent assembles a unified subject profile, expands the account into its full entity cluster on-chain, scores the network against sanctions and illicit-activity signals, and drafts an intelligence-rich SAR narrative — then hands a human a decision-ready package with a complete audit trail. It is the "investigator co-pilot" your own resume already references, made real.

**Why this one.** It fuses your three highest-scoring pain points into one story — **#1 (unified subject timeline)** as the orchestration spine, **#2 (cluster/network mapping)** and **#3 (high-quality SAR drafting)** as the two headline capabilities — and it leans directly on your two sharpest differentiators: on-chain graph fluency (Chainalysis/Elliptic/Leidos FININT) and SAR-pipeline leadership (your "same-day SAR pipeline architecture"). It satisfies the "balance of both" brief precisely: there is real, non-trivial engineering to show, but the spine of the story is a sophisticated compliance problem solved with obvious domain judgment.

### Architecture

A supervisor/orchestrator agent coordinating specialized sub-agents and tools, implemented as an explicit state machine so the control flow is legible (this legibility is a selling point — regulators and auditors care that an agent's steps are inspectable, and you can say so):

1. **Profile Aggregator** — tools that connect to several *mock* internal systems (KYC store, fiat + crypto ledgers, IP/device/session store, customer-service tickets, blockchain-intel feed). Returns a normalized, single timeline and auto-flags anomalies such as geolocation-IP vs. declared-residence mismatch and elevated VPN usage. *(covers pain point #1)*
2. **Network Expander** — seeds from the flagged account and walks the transaction/wallet graph 1–7 hops (mirroring the cluster-expansion tools investigators rely on), linking entities on shared attributes — device/session and `device_fingerprint` identifiers, reused KYC documents, and on-chain counterparty flows — and including a **gas-funding linkage** tool (who funded whose gas), a move that repeatedly exposes the controller behind a "non-custodial" address in documented investigations. Emits an interactive, risk-weighted network graph. *(covers #2)*
3. **On-chain Risk Scorer** — matches cluster addresses against a sanctions/illicit-address set and produces a consolidated risk read. A natural place to later graft in the **#8** "reconcile conflicting vendors" logic by simulating two scoring sources over the same addresses. *(seed of #8)*
4. **Remark/Tell Miner** — continuously mines user-generated free-text — withdrawal remarks, address labels, note fields — and fuzzy-matches it against sanctioned-entity names, transliterations, known aliases/nicknames, and entities already in the case graph. In documented investigations, attribution repeatedly breaks open on a single remark (an address labelled with its true controller's nickname, or "aggregation wallet"); this makes that systematic rather than lucky, and across languages. *(new — PP-11, promoted to headline)*
5. **RFI Contradiction-Checker** — decomposes a subject's RFI response into discrete factual claims and adversarially tests each against device data, on-chain flows, corporate-registry OSINT, and *the subject's own prior RFI answers*, emitting a claim-by-claim contradiction table with evidence pointers. Documented investigations turn on polished, legalistic RFI narratives (licensed-trust "segregation," "no ownership or management relationship") that are flatly contradicted by shared devices and fund flows — today only catchable by an investigator holding the whole case in their head. *(new — the sharpened, promoted core of #5)*
6. **Regulatory Advisory Matcher (FinCEN advisory RAG)** — maintains a searchable knowledge base of current FinCEN advisories and matches them to the unified profile and network. Event-triggered on RFI responses: when a reply from the flagged user *or* anyone in their cluster surfaces a key term (e.g., "oil" / "petroleum"), the matcher fuses that signal with structured corroborators already in the profile — jurisdictional nexus, name/entity hits, and on-chain links to flagged addresses — and, above a confidence threshold, attaches the specific advisory, the exact red-flag indicators it matched, and the SAR key terms FinCEN instructs filers to cite. *(regulatory grounding; see design notes below)*
7. **SAR Drafter + Critic (agentic loop)** — assembles case facts into a FinCEN-style SAR narrative with predicate-offense tagging, citing any advisory and specific red-flag numbers surfaced by the Matcher, the contradiction table from the RFI checker, and the tell attributions — then a separate Critic agent scores the draft against an "intelligence-rich vs. defensive" rubric and sends it back for revision until it clears the bar. This self-critique loop is the most *agentic* part of the system and dramatizes your signature thesis: fewer, higher-quality reports. *(covers #3)*
8. **Case Packager + persistent case graph** — compiles the profile, network graph, risk score, tell hits, RFI contradiction table, matched advisories, and SAR draft into a human-review package with a full, timestamped, append-only audit log of every access, action, and tool call. Every subject, address, device, and entity persists in a **case graph**, so at the next case open the agent surfaces "this subject/address/device already appeared in N prior cases" — the cross-case recidivism the real volume-driven queue kept missing (one account cleared five prior "retain & monitor" reviews before anyone connected it to the network).
9. **Designation-Triggered Remediation Sweep (v1.0 capstone)** — a *second entry point* over the same components: given a new OFAC designation (new SDN entity or crypto addresses), it sweeps the full synthetic ledger for directly and indirectly exposed accounts, verifies block status across the warehouse and admin systems (catching the data-integrity gaps documented in public enforcement actions), triages by exposure, and drafts a per-account remediation worksheet and escalations. Because it reuses the Risk Scorer, Network Expander, case graph, sanctions ingestion, and SAR/escalation drafter, its marginal cost is low — which is exactly why it's built last, as the capstone, rather than in the early core. Its regulator relevance is the highest in the system given the current aggressive posture of FinCEN's Iran program. *(PP-12 — promoted from roadmap to committed v1.0 scope)*

#### Design notes on the Advisory Matcher (viability)

This addition is highly viable and, more than that, it *upgrades the whole system's thesis* — it turns "this account is risky" into "this account matches FinCEN Advisory X, red flags 3 and 7, file citing key term Y," which is exactly the intelligence-rich output an FIU wants. A few design points make it robust rather than noisy:

- **Data is ideal.** FinCEN advisories are US-government public domain, published as 508-compliant PDFs with explicit, numbered red-flag indicators, named typologies, and prescribed SAR key terms — safe to ingest and even redistribute in a public repo. This is one of the cleanest possible data sources.
- **Use hybrid matching, not keyword-only.** Keyword/regex on the advisory's published key terms gives precision, but on its own it's brittle to obfuscation, code words, and other languages. Layer in semantic/embedding similarity and structured entity-and-graph matching (name → advisory named-entity list; address → advisory-referenced flagged addresses; jurisdiction → advisory scope). This is also where the roadmap's multilingual capability (#5) compounds — an RFI reply in Farsi or Mandarin still triggers.
- **Require corroboration; threshold the match.** Attach an advisory only when a key-term hit is joined by at least one structured corroborator (jurisdiction, entity, or on-chain link). Attaching every advisory on a lone keyword recreates the "defensive SAR" noise problem in a new form — the matcher should be as disciplined as the SAR rubric.
- **Treat name matches as leads, not conclusions.** Transliteration and alias noise make named-individual matching the classic false-positive trap; use fuzzy matching, always require corroboration, and present output as "possible match — evidence attached" with a confidence score for human confirmation, never as an asserted identity.
- **Keep the demo clean.** Match synthetic subjects against the advisories' real red-flag *indicators and typologies*, and demonstrate named-entity matching against a synthetic/illustrative watchlist — so the repo never fabricates an accusation against a real named person while still showing the capability end to end.
- **Note freshness as a production concern.** A static snapshot of a few current advisories is fine for the demo; document that production would refresh the corpus as FinCEN issues/updates advisories.

### Grounded in documented sanctions-evasion typologies (patterns only, no PII)

This design was pressure-tested against publicly documented Iranian-oil / "shadow-banking" typologies — FinCEN advisories, OFAC designations, and published exchange enforcement actions. We replicate *behavioral patterns*, never real identities, addresses, or documents. The review confirmed our top capabilities (cluster mapping, SAR quality, advisory grounding) and surfaced patterns strong enough to promote or add:

- **PP-11 tell mining** and the **RFI Contradiction-Checker** are promoted into the headline capability set above — in documented investigations these signals, more than blockchain analytics, are what actually crack attribution and expose false narratives.
- **Promoted to committed v1.0 capstone:** designation-triggered remediation sweeps (PP-12 — on an OFAC designation, auto-sweep the full ledger for exposed accounts, verify block status across systems, draft escalations). Highest regulator relevance given FinCEN's aggressive Iran program, and cheap to build last because it reuses the whole core (see architecture component 9).
- **Roadmap (post-v1.0), re-ordered by payoff:** ML alert auto-closure QA (PP-13 — re-adjudicate a sample of auto-closed alerts, "AI overseeing AI") and vendor reconciliation (#8) first; then tokenized-commodity issuance tracing (PP-14 — follow gas-funding chains from bespoke oil/gold/fiat-peg token deployers), the multilingual OSINT verifier (#5), and LE-request/MLAT routing (#4/#7).

**The synthetic demo scenario** is re-anchored on a fabricated but pattern-faithful oil/sanctions-evasion network, which exercises every capability at once and ties directly to the public FinCEN advisories. Its generator plants: a sanctioned oil-broker archetype using family members and an employee as cutout directors; a ring of shell trading entities across UAE / Türkiye / HK / NZ / China with near-identical websites and *reused KYC documents across supposedly separate entities*; a high-volume licensed-trust/custody intermediary whose polished RFI narrative is contradicted by cross-entity device sharing and a recent common controller; bespoke tokenized commodities deployed via gas-funded chains; a synthetic "IRGC-style" attributed address set with layered non-custodial hops, round-number structured transfers, and bidirectional near-equal flows; user remarks that betray true control; VPN + sanctioned-jurisdiction IP leakage; a recidivist account that cleared multiple prior "retain & monitor" reviews; and a "privileged / internal account" tag planted as a **red herring the agent flags for review rather than obeys** — the governance-capture failure mode documented in public enforcement actions, reframed as a control the system enforces.

### Public / synthetic data — everything is safe to publish

- **On-chain graph:** the **Elliptic** and **Elliptic++** datasets — a labeled graph of Bitcoin transactions and wallet addresses with illicit/licit tags — are purpose-built for exactly this and are publicly available.
- **Fiat/crypto transaction patterns:** use the **IBM "Transactions for AML" (IT-AML)** dataset — a large, pre-generated, perfectly-labeled synthetic set spanning multiple banks, currencies (including Bitcoin), and eight laundering typologies; **start with the HI-Small variant** (~5M transactions — workable size, realistic class imbalance). Note the naming: **AMLSim** is IT-AML's *predecessor and a simulator you run* (Python + Java) to plant bespoke laundering clusters — reach for it only if you want hand-crafted demo cases, not as the primary data source. **AMLNet** (third-party, CC BY 4.0) is an alternative whose per-transaction device/geo/risk-score fields are a good match for the Profile Aggregator's behavioral metadata.
- **Sanctions / illicit addresses:** **OFAC's SDN and Consolidated lists** are free official downloads (XML/CSV), and **OpenSanctions** offers a well-structured, developer-friendly version.
- **FinCEN advisories:** published openly on fincen.gov as 508-compliant PDFs (e.g., the June 2025 Iranian illicit-oil-smuggling / "shadow banking" advisory and the August 2025 Chinese Money Laundering Networks advisory), each with numbered red-flag indicators and prescribed SAR key terms — US-government public domain, safe to ingest and redistribute.
- **KYC, IP/device, CS tickets, withdrawal remarks & RFI narratives:** generate synthetically with Faker plus the scenario generator (see the demo scenario above), so no real person, address, or document ever appears in the repo — while the *patterns* (reused KYC docs, `device_fingerprint` device matches, Tehran-IP-between-VPN leakage, structured round-number transfers, false RFI narratives) stay faithful.

### Suggested tech stack

Python; an agent-orchestration framework (**LangGraph** for legible, inspectable state machines — its explicitness is a virtue here; **CrewAI** or **AutoGen** are fine alternatives); an LLM via API; **DuckDB/SQLite** for the mock stores; **networkx + pyvis** for the network graph; **Streamlit** (or a small FastAPI + HTML UI) for the demo; **pytest** for tests; Faker + the datasets above for data. All current and free.

### Scoped MVP vs. roadmap (this framing is part of the deliverable)

**MVP core (build first):** the orchestrator + Profile Aggregator (#1) + Network Expander with gas-funding linkage (#2) + Remark/Tell Miner (PP-11) + RFI Contradiction-Checker + Regulatory Advisory Matcher (FinCEN RAG) + SAR Drafter/Critic (#3), over Elliptic + the IBM IT-AML dataset (HI-Small) + OFAC + a snapshot of current FinCEN advisories + the synthetic oil/sanctions-evasion scenario, with a Streamlit demo and full audit logging. These are what make the generated SARs both regulator-grounded and genuinely investigative.
**Committed v1.0 capstone (build last, on top of the core):** the Designation-Triggered Remediation Sweep (PP-12). It's the most regulator-relevant capability in the system and, because it re-orchestrates finished components rather than adding a new subsystem, its marginal cost is low — the reason it's a capstone rather than an early-core item. Membership in v1.0 is decided on payoff-to-*marginal*-cost, not payoff alone.
**Roadmap (post-v1.0, re-ordered by payoff):** ML alert auto-closure QA (PP-13) and vendor reconciliation (#8) first; then tokenized-commodity issuance tracing (PP-14 — kept out of v1.0 despite its timeliness because it needs new contract-tracing tooling with little reuse), the multilingual OSINT verifier (#5), and LE-request/MLAT routing (#4/#7). Building these in public after launch keeps the repo visibly growing. Listing deliberately-deferred extensions with clear integration points shows scoping discipline.

### Suggested build milestones

1. **Foundations** — synthetic data generators + mock system connectors; load Elliptic and the IBM IT-AML dataset (HI-Small); stand up the OFAC/OpenSanctions matcher.
2. **The spine** — orchestrator + Profile Aggregator producing a unified, anomaly-flagged timeline end to end.
3. **The headline capabilities** — Network Expander with interactive graph, then the SAR Drafter + Critic loop.
4. **Polish for portfolio** — Streamlit demo, audit-trail viewer, README, architecture diagram, a short screen-capture GIF, tests, and a written "responsible-AI / human-in-the-loop" note.

### How to present it on GitHub (this matters as much as the code)

Open the README in *your* executive voice: frame the real-world problem (defensive SARs, cluster-level reviews, fragmented silos) the way a compliance leader briefs a board, then show the architecture diagram, then the demo GIF (the network graph and a sample generated SAR are your visual money-shots). Include a prominent **"Responsible AI & Audit Trail"** section — human-in-the-loop by design, every agent action logged, synthetic-data-only disclaimer, and a note on regulatory defensibility. That section is not boilerplate; for a compliance-exec audience it is arguably the single most differentiating thing in the repo, because it proves you build AI the way a regulator would want it built.

## 5. Alternatives, if you change your mind on scope

If you ever want a **clean standalone second project** that leans on a different differentiator, build **#5 — the multilingual document + OSINT verifier**. It ingests a synthetic source-of-wealth packet (say, a business-registration certificate in Mandarin), extracts entities, translates, cross-references a public corporate registry (OpenCorporates / GLEIF), and flags discrepancies such as a registration date that contradicts the user's operational claims. It's genuinely agentic (extract → translate → external tool call → reason about conflicts), and it's the one project that showcases your linguist background — a combination almost no other compliance candidate can claim.

If you prefer a **single standalone flagship** over the fused co-pilot, **#3 (SAR quality)** is the safest high-credibility pick and the fastest to a polished result, and **#2 (network graph)** is the highest visual wow. The fused co-pilot simply gives you all three at once under one narrative, which is why it's my primary recommendation.

## 6. Guardrails for a public compliance repo

- **Synthetic and public data only** — never real customer records, and don't publish real-company OSINT lookups tied to allegations. State this explicitly in the README.
- **Human-in-the-loop, always** — the agent prepares; a human decides and files. Frame it this way everywhere; it's both responsible and exactly what regulators expect.
- **Skip pain point #10 entirely** for public work — "AI that routes around VIP protections" is a reputational liability out of context, no matter how carefully the tiered-access logic is written.
- **Make the tamper-evident audit trail the centerpiece** — the decisive failure mode documented in public enforcement actions is governance capture: investigator access blocked, records made to vanish, "internal account" tags used to shield subjects. An append-only log of every access, action, and alert-closure — with provenance — is precisely the control that fails in those scenarios, so foreground it in the README as the thing this system gets right, not a footnote.

---

## Sources

- [IBM Transactions for Anti-Money Laundering (AML) — Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)
- [IBM AMLSim — GitHub](https://github.com/IBM/AMLSim)
- [Realistic Synthetic Financial Transactions for AML Models (IT-AML paper, arXiv)](https://arxiv.org/html/2306.16424v1)
- [AMLNet — Synthetic AML Transaction Dataset (Zenodo)](https://zenodo.org/records/16482144)
- [Elliptic Data Set for Anti-Money Laundering in Bitcoin](https://www.elliptic.co/media-center/elliptic-releases-bitcoin-transactions-data)
- [Elliptic++ Dataset — GitHub](https://github.com/git-disl/EllipticPlusPlus)
- [OFAC Sanctions List Service (official downloads)](https://ofac.treasury.gov/sanctions-list-service)
- [US OFAC SDN List — OpenSanctions](https://www.opensanctions.org/datasets/us_ofac_sdn/)
- [The best AI agent frameworks in 2026 — LangChain](https://www.langchain.com/resources/ai-agent-frameworks)
- [FinCEN Advisory on the Iranian Regime's Illicit Oil Smuggling (June 2025, PDF)](https://www.fincen.gov/system/files/advisory/2025-06-06/FinCEN-Advisory-Illicit-Oil-Smuggling-508.pdf)
- [FinCEN Advisory on Chinese Money Laundering Networks (August 2025, PDF)](https://www.fincen.gov/system/files/2025-08/FinCEN-Advisory-CMLN-508.pdf)
- [FinCEN Advisories index](https://www.fincen.gov/resources/advisoriesbulletinsfact-sheets/advisories)
