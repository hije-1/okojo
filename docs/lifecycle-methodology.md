# Counterparty-Designation Lifecycle — methodology (Phase 8 Part IV)

**Status:** Phase 8 Part IV — the last piece of component 9 (the
Designation-Triggered Remediation Sweep). This document is the published,
versioned **posture** for Okojo's counterparty-relationship lifecycle. It is
**prose only**: unlike the ten doc↔code anti-drift pairs, it carries **no
canonical config block of its own**. The layer's load-bearing policy — the
outcome set, the strict precedence, and the decision rule — lives in
`agency_config()` (`AGENCY_VERSION` ≥ 1.5.0) and is drift-protected by the
**agency** anti-drift pair (`docs/agency-methodology.md` §8,
`tests/test_agency_methodology.py`) and stamped into every counterparty sweep's
tamper-evident audit chain. This document explains the lifecycle *around* that
decision; it never restates the rule as a second, driftable source of truth.

Everything in this layer is **REVIEW-tier** and **calibrated**: the sweep
*drafts* a customer notification and *proposes* a relationship disposition; **a
human decides and acts**. Nothing here is executed.

All data is **synthetic**: the designated counterparty ("Kavelith Digital
Exchange", `DES-2026-0009`) is a **fictional** VASP, its addresses are invented,
and the four customer personas are synthetic.

---

## 1. What the counterparty lifecycle does

A new designation **kind** — **`counterparty_service`** — designates a *service*
(a VASP / exchange), not a person, a company officer, or a territory. Its on-chain
addresses are the counterparty's **hosted wallets**; the customers who transacted
with them are surfaced by the **existing** Part I flow sweep, and the S3
`exposure_timing` field already splits **pre-** from **post-designation** dealing.

Detection is therefore already done. Part IV adds only what happens **after
detection** — the relationship lifecycle for each customer who dealt with the
counterparty **after** it was designated:

1. a **drafted customer notification** (subject-facing, a Terms-and-Conditions
   matter);
2. a **record-only lifecycle state** each relationship has reached;
3. the **relationship disposition** — the eighth bounded agency decision
   (`decide_counterparty_lifecycle`: `propose_unblock` / `propose_offboard` /
   `hold_pending`); and
4. a **no-auto-unblock** hard rule, proven by test.

Pre-designation-only dealing earns a review with its full dossier but **no
notification** — the notification addresses *post-designation* dealing.

## 2. Lifecycle states

A relationship reaches the **furthest milestone its evidence supports**. The
milestones are linear on the happy path, with one divergent terminal for a repeat
offender (`derive_counterparty_lifecycle_state`, `src/okojo/sweep/lifecycle.py`):

| State | Meaning | Rendered as |
|---|---|---|
| `exposure_detected` | the customer dealt with the counterparty; nothing further recorded | exposure detected |
| `notification_drafted` | a subject-facing T&C notification has been drafted (never sent) | customer notification drafted |
| `acknowledgment_recorded` | a human-entered acknowledgment of **this** counterparty's designation is on file | acknowledgment recorded |
| `stop_dealing_verified` | no dealing with the counterparty's addresses is recorded **after** the acknowledgment date | stop-dealing verified |
| `unblock_proposed` | the disposition proposes lifting the restriction (happy-path terminal) | lifting the restriction proposed |
| `offboard_proposed` | the divergent terminal — a repeat offender leaves the happy path | offboarding proposed |

The state is **derived, never stored**: it is recomputed from evidence in hand on
every run, so it can never disagree with the disposition or the audit chain. The
proposal terminals (`unblock_proposed` / `offboard_proposed`) win over the bare
evidence milestones — a relationship whose disposition is a proposal reports the
proposal, not the milestone underneath it.

The **verified-stop cut is the acknowledgment date**, not the designation date
(ruling Q6): pre-acknowledgment post-designation dealing is exactly what the
notification addresses, and it does **not** bar a later unblock proposal if
dealing then stopped. A customer who acknowledges and keeps dealing has **no**
verified stop, and the relationship stays `hold_pending`.

## 3. The customer notification — disclosure policy

Each post-designation dealer is drafted **one** subject-facing notification: a
Terms-and-Conditions matter, grounded in the customer's own account row,
authored **guard-safe**, validated fail-closed by `assert_no_tipping_off` on the
fully rendered text, `drafted_pending_human_review` the **only** status, **no
send path**, and suppressed-and-surfaced (never silently dropped, never emitted)
on any grounding or guard failure.

The disclosure line the template walks is **widened but bounded** (ruling Q4).
The template says, in substance: *a counterparty your account dealt with has been
added to a public designation list; under the Terms of your account we conduct a
periodic review of dealings connected to designated counterparties and may apply
restrictions while that review completes; please contact us.* It names the
counterparty's **public designation** and the customer's **contractual
obligation** — both legitimately sayable — and deliberately chooses **more
calibrated** words ("designated / listed counterparty", "under the Terms", "may
apply restrictions") over the words that would tip off ("sanctioned", "blocked",
"frozen", "reported", "investigation"). The calibrated wording is the point, not
a workaround: the guard is not weakened; the text is authored to pass it, and
still validated after rendering as defense in depth (the interpolated customer
and counterparty names are the likeliest smuggling path).

## 4. Guard-surface map (the two-audience boundary)

The counterparty lifecycle produces **one subject-facing surface** — the customer
notification — and several **internal** ones (the lifecycle state and disposition
a reviewer reads, the decision rationale, the audit stamps). Which guard applies
is a function of **who could read the text**, never of the surface's name:

| Surface | Who reads it | Guard | On failure |
|---|---|---|---|
| Customer notification (T&C) | the **customer** (subject-facing) | `assert_no_tipping_off`, on the fully rendered text, plus grounding to the account row | suppressed & surfaced for human authoring; never sent |
| Lifecycle state / disposition / decision rationale | internal (compliance reviewer) | grounding to the rows read; calibrated language | flagged; a claim that cannot cite its row is never emitted |
| `counterparty_notification` / `counterparty_lifecycle` audit stamps | internal (audit) | provenance-pointed, chain-verified | — |

**What is sayable on the subject-facing surface:** the counterparty's **public
designation** (a public fact) and the customer's **contractual obligation** under
the account Terms (a legitimate reason to write).

**What is NOT sayable on the subject-facing surface**, and lives only in the
internal surfaces:

- the **evidence methods** (which addresses, which transactions, the exposure
  timing, the acknowledgment ledger, the repeat-offender determination);
- the **existence of any investigation** or internal review beyond the neutral
  T&C periodic-review language; and
- any **law-enforcement interest**.

The single rule behind the table: **only subject-facing text passes through
`assert_no_tipping_off`.** The customer notification is the sole subject-facing
surface this layer produces; everything else is internal analyst material that
legitimately names the counterparty, the dealings, the acknowledgment, and the
proposed disposition a customer must never see. The guard is chosen by the
**audience**, so no internal artifact is ever weakened to satisfy a subject-facing
rule, and no new subject-facing surface can be added without inheriting the
tipping-off guard by construction.

## 5. The hard rule — no auto-unblock

**Nothing in this layer mutates a hold.** The lifecycle module reads evidence and
emits records; the disposition — including `propose_unblock` — is a **REVIEW-tier
proposal for a human**, never an action. A human decides and applies any change to
a hold.

This is proven, not asserted, by two guard tests (`tests/test_lifecycle_eval.py`):
a **byte-snapshot** of both sanctions-hold tables (`sanctions_hold_warehouse.csv`,
`sanctions_hold_admin.csv`) is taken across a full run over the counterparty
designation and a domestic one and shown unchanged; and a **static backstop**
proves no module in the sweep package writes a CSV, the lifecycle module names no
hold table at all, and the read-only connector exposes no hold-mutation method.
There is, by construction, **no code path that could unblock an account** — only a
proposal record.

The real-world rationale is deliberate: an automatic unblock is precisely the
failure mode this capstone is built to *not* reproduce. A relationship that
resumes access the moment a box is ticked removes the human judgment that a
lifted restriction demands. Okojo builds the opposite — the unblock is a
**proposal a reviewer must apply**, gated on both a recorded acknowledgment and a
verified stop, and outranked entirely by recidivism.

**Modeling choice (disclosed):** in this synthetic scenario the four
review-subject personas carry no visible hold row, so an unblock proposal refers
to lifting **the sweep-proposed restriction** (the review-tier restriction this
sweep itself proposes); in production it would instead reference the
institution's **actual hold record** for the customer.
