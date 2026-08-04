# Audit-Narrator Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains how Okojo
turns its tamper-evident audit trail into a plain-language narrative a human can
read, why that narrative can be trusted to reflect the chain it came from, and
exactly which policy version produced it. It is the eleventh doc↔code anti-drift
pair, alongside scoring, retrieval, critic, contradiction, agency, casegraph,
packager, sweep, identity, and geo.

## What the narrator is

A grounded, **read-only** summarizer over the hash-chained audit trail. It reads
a chain and renders a plain-language narrative of what the agent did, in order,
and why — one sentence per record, each citing the exact record behind it. The
audit trail is Okojo's centerpiece control: tamper-evident and *provable*. The
narrator makes it *reviewable*, closing the loop from "provable" to "reviewable."

The narrator **writes nothing to any chain**. It has no side effects on the
evidence, the case graph, or the audit log; running it leaves every chain
byte-identical. Its version is therefore pinned **through the artifact** — every
narrative carries `narrator_version` — rather than by stamping a record into a
chain (the same pattern as `packager_config`).

## Verify first; a failed verification IS the narrative

Before any record is narrated, the chain is verified end-to-end with
`AuditLog.verify_chain_located()` — the located sibling of `verify()`, which reports
*where* a chain first breaks, not merely *whether* it is intact. Both share one
definition of "intact," so they can never disagree.

If the chain verifies, the narrator proceeds. If it does **not**, the narrative
*is* the break report: a single sentence naming the record position where
verification first fails, its failure reason (`seq_out_of_order`,
`prev_hash_mismatch`, or `hash_mismatch`), and the count of records that verified
before the break. Content at or beyond the break is **never** summarized — a
broken link makes everything past it untrustworthy, so the narrator withholds it
and refers the record to a human. This is the reading-surface analogue of the
system's fail-closed discipline: a chain that cannot be trusted is reported, not
narrated over.

## Grounding contract (fail-closed)

The grounding contract applies in full. Each narrative sentence carries a
`RecordRef(seq, hash)` — a pointer to the specific record it reads.
`assert_narrative_grounded` builds a membership set over the verified chain's own
`(seq, hash)` pairs (the narrator's analogue of the SAR `GroundingResolver`, but
over records rather than evidence rows) and **rejects** any sentence whose
citation does not resolve. A fabricated or dangling citation fails closed, exactly
as an uncitable SAR claim does. Because the narrator builds each sentence *from* a
record, a faithful narrative always passes; the guard exists to catch anything
injected after the fact.

## Calibrated language

Narrator output is screened with the SAR drafter's **exact** `BANNED_TERMS` tuple
(imported, not re-declared, so there is one source of truth). It narrates what was
recorded — "stamped / drafted / proposed / flagged / recorded" — and
`assert_calibrated` rejects any sentence that reaches for over-claiming language
("instantly", "autonomously", "guaranteed", "proven fact", "definitely",
"certainly").

## Why templates, and why no LLM

Narration is a deterministic `(actor, action) → sentence` template map. There is
**no LLM leg.** Two reasons, both load-bearing:

* **Faithful reading.** A template is a 1:1 reading of the record — it restates
  what the record says, in plain language, and nothing more. An LLM summarizer
  would be free to compress, infer, or embellish, which is precisely the
  failure mode a *reviewable audit trail* must not have. The narrator's job is
  to make the record legible, not to interpret it.
* **Determinism and the eval.** A template map yields byte-deterministic output
  per chain, so the narrative can be regression-tested and its grounding scored.
  The eval (grounding P/R over planted chains, a tampered-chain fixture, an
  ungrounded-injection falsification) depends on that determinism.

Records are narrated in two registers: **setup** records — `tool_call`, the
versioned `*_config` policy stamps, `embedder_active`, and `graph_rendered` — are
de-emphasized as provenance; **action** records carry the consequential steps.
Template coverage is **additive**: a record without a family-specific template
still narrates faithfully via a generic reading, so extending coverage to the
sweep and batch families does not itself move the version.

## Scope

v1.0.0 covers all four chain families over one set of shared machinery
(`verify_chain_located`, the grounding resolver, the calibration guard, the
two-register artifact):

* **Case** — the 14-actor case chain the compiled pipeline writes.
* **Sweep** — the Designation-Triggered Remediation Sweep's own chain, over two
  actors (`remediation_sweep`, `sweep_packager`) and 19 actions. Each template is
  a faithful 1:1 reading of the record's own detail — it reports the counts and
  identifiers the record carries and nothing more — with the three versioned
  policy stamps (`sweep_config`, `identity_config`, `geo_config`) in the setup
  register and every consequential step in the action register.
* **Batch** — a whole list drop. A batch owns **no chain of its own**: it is N
  independent sweep chains plus a derived, non-chained `rollup` dict. So its
  narrative is exactly that — each constituent sweep chain narrated on its own
  terms (break-report-only where one fails verification), plus a **roll-up whose
  every sentence is grounded to a real record in a constituent chain** (the
  terminal `sweep_complete` of a verified chain, read for its own counts, or the
  break-position record of a broken one). The `rollup` dict is a view, **never a
  grounding source**; a broken constituent is reported and excluded from the
  roll-up, never summarized past its break.
* **Coverage** — the institution-level screening coverage-gap assessment's own
  chain, over one actor (`coverage_assessment`) and five actions (open, the
  versioned policy stamp, footprint, finding, complete). Each template is a
  faithful 1:1 reading of the record's counts, with the policy stamp in the
  setup register and the footprint / finding / complete steps in the action
  register. Read-only: the assessment writes only its own chain, so no case or
  sweep chain moves.

Template coverage is additive by construction: an unknown record still narrates
faithfully via the generic reading, so extending the map never moves the version.

## Versioned policy (canonical)

The block below is the single source of truth for the narration policy, compared
byte-for-value against `narrator_config()` by `tests/test_narrator_methodology.py`
so the doc and the code can never silently drift.

<!-- narrator-config:begin -->
```json
{
  "version": "1.0.0",
  "narration": "one sentence per audit record (1:1), in the order recorded; setup records (tool_call, *_config, embedder_active, graph_rendered) render in a de-emphasized register, consequential actions in the action register",
  "determinism": "a deterministic (actor, action) -> sentence template map; no LLM. A template is a faithful 1:1 reading of the record, so the narrative is byte-deterministic per chain and the eval holds",
  "grounding": "every sentence cites the specific record it reads by (seq, hash); validation is fail-closed — a sentence whose citation does not resolve to a real record in the verified chain is rejected",
  "calibration": "narrator output is screened with the SAR drafter's exact BANNED_TERMS tuple; over-claiming language is rejected",
  "verification": "the chain is verified FIRST; a chain that fails verification is reported as the narrative itself (the break located and cited, the count that verified before it stated), and content at or beyond the break is never summarized",
  "read_only": "the narrator writes NOTHING to any chain; its version is pinned through the narrative artifact (like packager_config), never stamped into a chain",
  "scope": "all chain families (case, sweep, batch, coverage); records lacking a family-specific template still narrate faithfully via a generic reading, so template coverage is additive and does not itself move the version"
}
```
<!-- narrator-config:end -->
