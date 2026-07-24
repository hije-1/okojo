# Agentic Crypto-Investigations Co-Pilot — Dated Build Plan

**Builder:** Jennifer Hicks
**Cadence:** ~20 hrs/week (4–5 hrs/day Mon–Fri, light weekend overflow)
**Start:** Tuesday, July 21, 2026
**Targets:** demoable walking skeleton by **~Aug 8**; core MVP polished by **late October**; v1.0 including the remediation-sweep capstone by **~early December**, with the reliability buffer kept intact (to **~Dec 5**).

This plan builds the flagship from the strategy doc. It bakes in the eight expert-review fixes (agentic decision points, an evaluation harness, the Elliptic↔OFAC address-space correction, SAR grounding controls, an operationalized SAR rubric, calibrated language, right-sized scope, and a broader regulatory frame) *and* the two capabilities promoted after pressure-testing the design against publicly documented investigation typologies: the **Remark/Tell Miner** (PP-11) and the **RFI Contradiction-Checker**. Those two additions grew the plan by ~2 weeks versus the original 16. A further ~2 weeks are committed for the **Designation-Triggered Remediation Sweep (PP-12)** capstone — promoted into v1.0 for its regulator relevance (FinCEN's aggressive Iran program) and cheap to build last because it reuses the entire core — bringing the plan to ~20 weeks with the reliability buffer protected.

## Guiding principles

- **Walking skeleton first, then thicken.** Get one synthetic case flowing end-to-end through a thin version of every stage before making any single stage good. This de-risks integration early and gives you something to show fast.
- **Publish early and build in public.** The moment the skeleton works (~Aug 8), push it to a public GitHub repo — rough is fine. A visible, steady commit history while you're job-hunting is itself a portfolio signal, and you can reference the repo in applications weeks before it's "done."
- **Patterns, never PII.** Everything is synthetic. The demo scenario replicates the *behavior* of real oil/sanctions-evasion networks (shell-entity rings, reused KYC docs, gas-funded token deployers, false RFI narratives, `device_fingerprint` device matches, structured round-number flows, a red-herring "internal account" tag) — no real identities, addresses, or documents ever enter the repo.
- **Reserve the last stretch for reliability.** The tail — no hallucinated SAR facts, the graph always renders, the Critic and RFI-checker loops always converge — is where agentic systems overrun. The plan holds ~3 weeks of buffer at the end for exactly this.

## Phased timeline

### Phase 0 — Foundations (Week 1: Jul 21–25, ~16 hrs)
- Bootstrap repo: Python env, pinned deps, MIT license, README stub with the "what this is / what this is NOT" disclaimer (synthetic research prototype; not production screening; not legal advice; not a filing tool).
- Stack decisions locked: LangGraph (orchestration), Chroma or FAISS (advisory RAG), DuckDB/SQLite (mock stores), networkx + pyvis (graph), Streamlit (UI), pytest (tests), RapidFuzz (tell matching).
- Download and sanity-check data: Elliptic/Elliptic++, IBM IT-AML **HI-Small**, OFAC SDN (incl. digital-currency addresses), 2–3 FinCEN advisories (Iran illicit-oil / shadow banking; China CMLN).
- **Synthetic scenario generator v0** and the Faker persona layer: emit KYC/identity records, `device_fingerprint` device matches, IP/session logs, withdrawal-remark and note fields, and RFI-response text — bound onto IT-AML account IDs. Plant the first oil/sanctions-evasion motifs (a shell-entity pair with reused KYC docs; a couple of deliberate anomalies: IP-geo vs. declared residence, VPN, a telltale remark).
- **Milestone:** repo bootstrapped, data loads clean, one synthetic subject with remarks + device data exists.

### Phase 1 — Walking skeleton, end-to-end (Weeks 2–3: Jul 28–Aug 8, ~40 hrs)
- Mock system connectors (KYC, ledger, IP/device, CS tickets, remarks) as simple tools over DuckDB/JSON.
- Profile Aggregator produces a unified, anomaly-flagged timeline for one subject; surfaces any raw remark hits (basic string match for now).
- Minimal LangGraph orchestrator wiring the nodes; append-only audit logging from day one.
- Minimal Network Expander: a small 1–2-hop subgraph from Elliptic with a static pyvis render.
- One FinCEN advisory ingested; simple keyword+semantic match triggered by an RFI string ("oil").
- A bare, grounded SAR draft (structured output, no Critic yet).
- Minimal Streamlit page: timeline + graph + matched advisory + draft.
- **Milestone (~Aug 8): demoable walking skeleton. Publish to GitHub. Record a first rough demo GIF.** This is the artifact you can start citing in applications.

### Phase 2 — Graph, gas-funding & tells (Weeks 4–5: Aug 11–22, ~40 hrs)
- Full Network Expander: 1–7-hop expansion, risk-weighted nodes, interactive graph, shared-attribute linking (`device_fingerprint`/device + reused-KYC-doc edges), and a **gas-funding linkage** tool (who funded whose gas) — a move that repeatedly unmasks "non-custodial" controllers in documented cases.
- **Remark/Tell Miner v1 (PP-11):** fuzzy-match remarks/labels/notes against the synthetic SDN/alias list and case-graph entities (RapidFuzz), across transliterations and nicknames.
- On-chain Risk Scorer **with the address-space fix**: keep Elliptic for graph/illicit-classification; add an *explicitly labeled synthetic address-tagging layer* for the OFAC-style sanctions match (don't conflate Elliptic's anonymized nodes with OFAC's real addresses).
- Evaluation harness v1: precision/recall/F1 on illicit-node detection vs. Elliptic labels (train/test discipline).
- **Milestone:** credible network + gas-funding + tell capability, reported with a metric.

### Phase 3 — Advisory Matcher (RAG) hardening (Weeks 6–7: Aug 25–Sep 5, ~40 hrs)
- Ingest 3–5 advisories; hybrid retrieval = keyword/regex on published key terms + semantic similarity + structured entity/jurisdiction/address matching.
- Corroboration rule enforced (key-term hit + ≥1 structured corroborator; thresholded); map each match to numbered red-flag indicators and prescribed SAR key terms.
- Shared entity store deduped with the sanctions screener and the tell miner (one entity backbone).
- Evaluation: false-positive rate on advisory matching, on crafted test cases.
- **Milestone:** robust, non-noisy advisory matching with evidence trails.

### Phase 4 — SAR Drafter + Critic + grounding (Weeks 8–9: Sep 8–19, ~40 hrs)
- Grounding contract: the drafter asserts only facts traceable to a tool output or evidence record; every claim carries a provenance pointer; schema-validated output; a validation pass rejects uncitable statements.
- Critic loop scoring against an operationalized FinCEN rubric (who/what/when/where/why/how; predicate-offense ID; subject-and-network characterization; on-chain evidence), with a max-iteration cap and human fallback.
- Evaluation: SAR-quality rubric scoring on a held-out set; ablation with/without Critic.
- **Milestone:** grounded, self-critiquing SAR generation.

### Phase 5 — RFI Contradiction-Checker (Weeks 10–11: Sep 22–Oct 3, ~40 hrs)
- Decompose a synthetic RFI response into discrete factual claims (structured extraction).
- Adversarially test each claim against device data, on-chain flows, corporate-registry OSINT, and the subject's *own prior RFI answers*; emit a claim-by-claim contradiction table with evidence pointers and a confidence per claim.
- Feed the contradiction table into the SAR Drafter so the narrative cites specific rebuttals.
- Evaluation: precision/recall of flagged contradictions against the scenario's known ground-truth lies.
- **Milestone:** the investigative headline capability — false RFI narratives caught automatically. Refresh the public demo + GIF.
- **Deferred, by design — "contradictions corroborate who/what/why" (post-Phase-5, its own slice).** In Phase 5 a confirmed contradiction is *additive*: it enters the SAR narrative citing both the assertion and its rebuttal, but satisfies no FinCEN-rubric element, so the Critic's version, gold key, and ablation are untouched. That is a scope decision, not an oversight — a rebutted false narrative is genuinely evidence of *what* happened and *why* it is suspicious, and mapping `contradiction` into those rubric elements should lift the Critic's recall on subjects whose other evidence is thin. It is deferred so the change is measurable: it needs its own `CRITIC_VERSION` bump, a re-authored rubric gold key, and a before/after ablation that reports the recall lift, rather than being folded into a phase that would mask it.

### Phase 6 — Genuine agency, case-graph memory & audit (Weeks 12–13: Oct 6–17, ~40 hrs)
- Convert the fixed pipeline into bounded agentic decision points: expand another hop? pull a second advisory? re-RFI? evidence sufficient to draft? SAR clears the bar? Frame the deterministic backbone as a *compliance feature* with autonomy confined to safe, bounded choices.
- **Persistent case graph:** every subject/address/device/entity persists; at case open the agent surfaces prior-case recidivism (the "cleared five reviews" failure mode).
- Full tamper-evident audit trail + Case Packager producing the decision-ready package; the "internal account" red-herring tag is *flagged for review, not obeyed*.
- **Milestone:** genuinely agentic over an auditable, recidivism-aware backbone.

### Phase 7 — UI, portfolio polish & the last 20% (Weeks 14–15: Oct 20–31, ~40 hrs)
- Streamlit UX: case selector, timeline, interactive graph, tell hits, advisory panel with cited red flags, RFI contradiction table, SAR view with provenance highlights, audit-trail viewer.
- Reliability hardening (the tail): no fabricated SAR facts, graph always renders, loops always converge.
- README in your executive voice (board-brief framing), architecture diagram, a prominent **"Responsible AI & Tamper-Evident Audit Trail"** section (foregrounding the governance-capture lesson), a calibrated-language pass, and a polished demo GIF/screencast.
- **Milestone:** portfolio-ready v1.0.

### Phase 8 — Designation-triggered remediation sweep (v1.0 capstone) (Weeks 16–17: Nov 3–14, ~40 hrs)
- A second orchestration entry point over the finished core: input a new OFAC designation (SDN entity and/or crypto addresses) and sweep the full synthetic ledger for directly and indirectly exposed accounts.
- Verify block status across the warehouse and admin mock-systems (a data-integrity reconciliation gap documented in public enforcement actions), and triage exposed accounts by exposure size and hop distance.
- Auto-generate a remediation worksheet (per-account status, exposure, recommended action) and draft escalations — reusing the SAR/escalation drafter and grounding contract.
- Evaluation: recall of exposed accounts vs. the scenario's known ground-truth network; false-positive rate on the sweep.
- **Demo money-shot:** paste in a designation → the system surfaces every exposed account and produces the remediation worksheet. This becomes a README headline.
- **Milestone:** the highest-regulator-relevance capability, built cheaply on top of the core. Refresh the demo + GIF.

### Phase 9 — Buffer, launch & narrative (Weeks 18–20: Nov 17–Dec 5, flexible)
- Absorb overruns (agentic builds always overrun somewhere).
- Companion essay in your exec voice — designing agentic AI for regulated compliance workflows, using the sanctions-evasion scenario as the worked example. High-leverage while job-hunting.
- **Audit Narrator (post-v1.0, high priority / low marginal cost).** A grounded summarization agent over Okojo's own hash-chained audit log, producing (a) a plain-language case narrative — what each agent did, in order, with citations to the log entries behind every sentence — and (b) an access review for auditors: activity grouped by actor and pattern, with unusual access surfaced as flags for human review (never conclusions). Rationale: raw access/audit logs in real institutions are endpoint-level clickstream that even experienced practitioners struggle to read; a tamper-evident log that no one can read still hides anomalies in plain sight. The Narrator makes the centerpiece audit trail legible, closing the loop from "provable" to "reviewable." Marginal cost is low: the input is the structured, provenance-carrying log Okojo already emits. Candidate to pull into v1.0 if schedule cushion allows.
- Optional, if time remains: begin the next roadmap module — ML alert auto-closure QA (PP-13) or vendor reconciliation (#8).
- **Milestone:** launched, documented, and shareable.

## At-a-glance

| Phase | Dates | Focus | Key deliverable |
|---|---|---|---|
| 0 | Jul 21–25 | Foundations | Repo + data + synthetic scenario v0 |
| 1 | Jul 28–Aug 8 | Walking skeleton | **Demoable end-to-end; publish to GitHub** |
| 2 | Aug 11–22 | Graph + gas-funding + tells | Network + Remark Miner, with a metric |
| 3 | Aug 25–Sep 5 | Advisory RAG | Robust advisory matching |
| 4 | Sep 8–19 | SAR + Critic | Grounded, self-critiquing SAR generation |
| 5 | Sep 22–Oct 3 | RFI Contradiction-Checker | False RFI narratives caught automatically |
| 6 | Oct 6–17 | Agency + case-graph + audit | Agentic, recidivism-aware, auditable |
| 7 | Oct 20–31 | UI + polish | Polished core (pre-capstone) |
| 8 | Nov 3–14 | Remediation sweep (capstone) | Designation → exposed-account sweep + worksheet |
| 9 | Nov 17–Dec 5 | Buffer + launch | Launched v1.0, documented, companion essay |

**Total:** ~20 weeks × 20 hrs ≈ 400 hours, with the final ~3 weeks as deliberate buffer and the remediation-sweep capstone committed inside v1.0.
