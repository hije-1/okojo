# Designation-Check Methodology (v1.1)

**Status:** synthetic-data research prototype. This document explains Okojo's
**subject-as-seed designation check** — the case-side mirror of the
Designation-Triggered Remediation Sweep. Where the sweep answers *"a designation
arrived — who is exposed?"*, the check answers the reverse question an
investigator actually asks in case mode: *"I have a subject in front of me — do
they, or their network, touch **any** designation?"* It is written for three
readers at once — an investigator, a model-risk reviewer, and an external
auditor.

Unlike the scoring, retrieval, critic, contradiction, agency, casegraph,
packager, sweep, identity, geo, and narrator layers, this layer ships **no
versioned config block and no doc↔code anti-drift pair** — deliberately. It
introduces no tunable constant: the badge state-machine and the coverage
statement are *derivation logic*, covered by tests, not policy dials. Everything
it screens with — the variant rules, the exposure thresholds, the corroboration
weights, the geo signals, the list-source registry — is owned by the engines it
reuses read-only, and each of those already publishes its own versioned
methodology. If a tunable constant ever appears here, that is version pressure
and a stop-and-show, not a silent addition.

Three principles govern everything below.

1. **It reuses the core; it never moves it.** The check is a pure, read-only
   composition of machinery the sweep / identity / geo / agency layers already
   own. It re-derives no score, no variant rule, no lifecycle state — it seeds
   those engines with the subject and reads back what they say. It writes to no
   store and mutates nothing.
2. **It surfaces and flags; a human decides.** The check produces a posture
   badge, exposure lines, a territory read, network notices, and a coverage
   statement — every one a *surface* or a *flag* carrying its evidence pointer.
   No hold is placed, no disposition is proposed, no message is sent.
3. **Proof-of-screening is an audit fact.** Every case run stamps exactly one
   `designation_check` record into the case's tamper-evident chain, whether or
   not anything matched — because *"did you check?"* is the regulator's first
   question, and the honest answer must be provable, not assumed.

---

## 1. What the check screens

The cluster it screens is the case's **own** Network-Expander reach at the
selected hop cap (`reached_account_uids`) — exactly what the investigator sees
on the Network tab, so the check and the graph can never disagree about who is
"in" the case.

Over that cluster it composes, for every designation in the table:

- **Party listings** (`sdn_style` / `national_ct` / `counterparty_service` —
  every non-territory row):
  - a **name + transliteration-variant screen** (the identity layer's variant
    rules), scoped to the cluster;
  - **address membership** — a controlled address that is itself a designated
    address;
  - **flow exposure** — funds reaching a designated address, with hop distance,
    tainted amount, direct/indirect, and the **pre/post/timeless designation
    timing split** (see §3);
  - **corroboration** against the designation's published identifiers, where it
    carries them (see §2);
  - the **counterparty lifecycle *state*** where the subject is exposed to a
    counterparty-service listing — display-only, no proposal.
- **Territory listings**: the geo dossier assembled *for the subject* per
  designated territory (the one-signal rule surfaces it, or a clean line).
- **Coverage**: a visible-absence statement naming every declared-but-not-
  ingested list, so the boundary of what was screened is a documented fact.

The **badge reflects the subject's own posture only**. A match or exposure
anywhere else in the cluster is a **network notice** that names the entity, the
designation, and the hop distance — never a badge escalation. The badge answers
exactly one question: *is this subject a match?*

---

## 2. The badge state-machine

The headline badge is derived from the subject's **own** active hits:

- **RED — `match_corroborated`** — the subject has a name/variant hit that is a
  **corroborated true hit**: the designation's published identifiers (date of
  birth, nationality, document) align with the subject's KYC.
- **AMBER — `possible_match`** — the subject has any other active hit: a
  name/variant match with no disqualifying identifier (or a
  `possible_match_needs_human` verdict), or a designated-address membership.
- **GREEN — `no_match`** — the subject has no active name/variant/address hit,
  **or** the only hit is a `name_only_dismissed` collision.

### Why a dismissed collision is GREEN, not amber (the Q2b rule)

A `name_only_dismissed` hit is a name that collided with a designated name and
was then **adjudicated away** because the published identifiers *disqualify* the
match (wrong date of birth, wrong nationality, wrong document). An adjudicated
collision is not an open item — so it does **not** hold the badge at amber.
Amber-forever on a settled question trains investigators to ignore amber; that
is the failure mode the rule exists to prevent.

But GREEN must not *hide* the work. So a dismissed collision always renders a
**standing, always-visible dismissal line** directly under the badge — cited,
never tucked in an expander — stating that a name collision was screened and
dismissed on identifier mismatch. This is the honest face of visible absence:
the clean conclusion **and** the work that produced it, both on screen.

### One green badge, non-clean lines beneath it (the Q2a rule)

A subject can be GREEN on the party badge and still carry a live exposure line —
e.g. not on any list, yet funds reach a designated address. These are *different
facts*, shown separately. The badge and the exposure lines render as **one
visual block**, and any non-clean line carries warning styling, so the green
badge never reads as an all-clear for the whole block — only for the one
question it answers.

---

## 3. Timing parity — the mirror is pinned to the answer key

Flow exposure carries a **timing** label: `timeless_control` (the subject
*controls* a designated address — hop 0, no time dimension), `post_designation`
(a cited driving transaction post-dates the listing), or `pre_designation`
(exposure predates it). The check computes this with a **local mirror** of the
sweep's own private helper — an independent read of the *same* evidence.

Because two engines now read the same fact, they could silently diverge. They
cannot: an explicit eval (`tests/test_designation_check_eval.py`) pins the
check's per-uid timing to the generator's `designation_exposure_timing` answer
key for **every** exposed (designation, uid) pair. The answer key is the
arbiter; drift is a red test, not a surprise in production.

---

## 4. Hit metadata, in plain language

Every surfaced hit carries its designation's metadata rendered for a human: the
program, the source regime, the list type, the listed-since date, and — the one
that changes what an investigator does — whether the list is a **blocking
obligation** or an **early-warning signal**:

- an **obligation** list → *"a blocking-obligation list"*;
- a **signal** list → *"an early-warning signal list, listed since <date>"*.

The distinction is doctrine, not decoration: an obligation binds; a signal is
cross-list early warning that a human weighs. The check never collapses the two.

---

## 5. The audit record (proof-of-screening)

Each case run stamps **one** `designation_check` / `screened` record into the
case chain, on the unconditional backbone right after the risk/sanctions stage.
The record embeds the **conclusion** — the badge state, the coverage counts, and
the corroboration outcome plus mismatched-field rationale (with evidence cites)
for each subject hit and dismissal — so the tamper-evident chain proves not just
*that* the subject was screened but *what the screen concluded*. The record is
read by the Audit Narrator like any other; adding it grew the case vocabulary by
one actor (13 → 14), which is additive template coverage and moves no version.

---

## 6. Known demo fact (corrected for v1.1)

The clean-state baseline applies to the **core roster** (uid 0–11): those
subjects carry no planted territory data, so their territory line is always
clean, and nothing is planted on them to force a badge. The **persona subjects**
— the identity, geo, and counterparty personas — are selectable case subjects
and **light up live**: the corroborated identity persona is RED, a geo persona
surfaces a territory signal, a counterparty persona shows a lifecycle state. A
walkthrough uses a persona subject for the lit states and a core-roster subject
for the clean baseline.

---

## 7. Why this lives in the investigator's own tool

The design intent, in the words that set it:

> The investigator lives in case mode; whatever is prudent to know about a
> subject must be apparent in the investigator's own tool; nothing an
> investigator needs is excluded.

The ledger-wide sweep is the right entry point when a *designation* is the seed.
But an investigator working a *subject* should not have to leave case mode, seed
a sweep, and cross-reference to learn whether that subject touches a list. The
check brings the sweep's own read-only engines to the subject, on the tab where
the investigator already is — and stamps the answer into the record so it is
provable later.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public
(OFAC SDN structure, FinCEN advisory red-flag typologies). No real identities,
addresses, or documents are used. This prototype prepares evidence for a human
reviewer; it does not screen, advise, or file.*
