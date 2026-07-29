"""Bounded agentic decision points (Phase 6).

Each decision is a PURE function of the evidence state: same evidence, same
outcome, every time. "Agency" here means rule-based, bounded, auditable
branching — never stochastic or model-driven wandering. Every rule below:

* takes only explicit evidence arguments (never the graph state, never a
  ground-truth label, never a claim/subject id);
* returns a :class:`DecisionRecord` carrying BOTH a precise technical
  ``rationale`` (the audit-exact wording) and a ``plain_language`` gloss (the
  same decision in compliance-officer terms — what a SAR investigator reads);
* is stamped into the tamper-evident audit chain by the orchestrator, with the
  driving evidence, so the full decision trace is reproducible and reviewable.

The thresholds are tunable policy parameters, not constants of nature; they are
published (with rationale) in ``docs/agency-methodology.md``, exposed through
:func:`agency_config`, stamped into the audit trail once per run, and
regression-tested against the doc so code and public methodology cannot drift.

Hard boundaries (also published in the methodology doc):

* a second advisory match is *surfaced to the analyst only* — the SAR drafter
  consumes the primary match alone;
* follow-up RFI material is *prepared as discrete routine requests* for the
  human investigator, who owns assembly, sequencing, and sending — the agent
  never sends anything;
* an insufficient-evidence case is *referred to a human* — no draft is
  attempted and nothing is fabricated.

Subject-facing text is governed by a **disclosure & anti-tipping-off policy**
(see the methodology doc): requests may cite only the subject's own records
and routine documentation asks, are built from neutral administrative
templates, and every rendered request must pass the fail-closed
:func:`assert_no_tipping_off` validator before it is surfaced — internal
artifacts (the SAR draft, the case package, this module's rationales) use the
real vocabulary; text meant for a subject's eyes never does.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from pydantic import BaseModel

from ..advisory import AdvisoryMatch
from ..rfi import ContradictionTable
from ..sar import CritiqueHistory

# Bump on any change to a threshold, outcome set, decision rule, or the
# follow-up disclosure policy. Stamped into the audit trail and mirrored by
# the published methodology doc.
# 1.2.0 — DecisionRecord carries row-level provenance (audit-stamped with
# each decision; per-decision semantics in the methodology doc).
# 1.3.0 — Part II adds the `corroboration` decision point (identity match vs
# a designation's published identifiers). It is stamped into the remediation
# sweep's chain as a recorded decision, not a case-graph routing branch — the
# sweep stays linear (see docs/identity-methodology.md).
# 1.4.0 — Part III adds the `geo_action` decision point (the seventh): for a
# TERRITORY designation, a surfaced account's geo totality dossier is scored
# into a net presence score and mapped to a REVIEW-tier proposal. Like
# corroboration it is a remediation-sweep decision — recorded, not routed (see
# docs/geo-methodology.md). The signal weight classes and counter-evidence
# categories are geo's (geo_config, frozen 1.0.0); the numeric weights, bands,
# and the mapping rule are decision policy and live here.
AGENCY_VERSION = "1.4.0"

# --- Tunable policy thresholds (see docs/agency-methodology.md) --------------

# Keep expanding while the last hop discovered at least this many new accounts
# (a hop whose frontier is empty is a no-op, so stopping is provably lossless).
EXPAND_MIN_NEW_ACCOUNTS = 1

# Surface a runner-up advisory when at least this many corroborated matches
# survived the corroboration gate.
SECOND_ADVISORY_MIN_MATCHES = 2

# Recommend a follow-up RFI when at least this many claims were adjudicated
# ``contradicted`` (the only flag verdict — qualified/unverifiable never
# trigger a re-RFI recommendation).
RE_RFI_MIN_CONTRADICTED = 1

# Minimum grounded timeline events for a draft attempt: with a resolved
# subject and one event, "who" and "when" are groundable — the least the
# fail-closed drafter needs to attempt a citable narrative.
SUFFICIENCY_MIN_EVENTS = 1

# --- geo_action policy (Part III): totality dossier -> a proposal ------------
# The numeric weights the geo signal WEIGHT CLASSES (geo_config, frozen) map to
# when a geo totality dossier is scored. A distinctive locator (a region-locked
# carrier, a VPN-slip) outweighs an ordinary IP hit, which outweighs a coarse
# timezone. Tunable policy, published in docs/geo-methodology.md and here.
GEO_SIGNAL_WEIGHTS = {"high_value": 3, "standard": 2, "weak": 1}

# The subtraction each COUNTER-EVIDENCE staleness status carries. A residency
# document issued OUTSIDE the territory argues against presence; a VALID one in
# full, an EXPIRED one only weakly (degraded), a MISSING one not at all. Staleness
# ONLY degrades the subtraction — it is never read as evidence of presence, so it
# never adds to the score. (VPN markers are never scored at all.)
GEO_COUNTER_WEIGHTS = {"valid": 3, "expired": 1, "missing": 0}

# The net-presence-score bands, weakest proposal first: each entry is the
# INCLUSIVE upper bound of net score N for that outcome. Above the last bound the
# score maps to GEO_ACTION_TOP. Single source of truth for both the rule below
# and the agency_config stamp, so the two cannot drift.
GEO_ACTION_BANDS: tuple[tuple[int, str], ...] = (
    (0, "no_action_totality_resolves"),
    (2, "propose_edd_rfi"),
    (4, "propose_withdrawal_only_restriction"),
    (7, "propose_trade_and_withdrawal_block"),
)
GEO_ACTION_TOP = "propose_full_block_and_escalate"

# The decision points and their closed outcome sets. For the five case-pipeline
# points the outcome strings double as LangGraph routing keys, so the branch
# taken is exactly the outcome recorded in the audit trail. The sixth and
# seventh, `corroboration` and `geo_action`, are REMEDIATION-SWEEP decisions
# (Parts II & III): they are recorded, not routed — the sweep has no branch to
# take, so the outcome drives review triage, never control flow.
DECISION_OUTCOMES: dict[str, tuple[str, ...]] = {
    "expand_hop": ("continue", "stop_cap", "stop_frontier_exhausted"),
    "second_advisory": ("pull_second", "single_match", "no_match"),
    "re_rfi": ("recommend_re_rfi", "no_contradictions", "not_applicable"),
    "sufficiency": ("sufficient", "insufficient"),
    "sar_bar": ("clears_bar", "human_review"),
    "corroboration": (
        "corroborated_true_hit", "possible_match_needs_human",
        "name_only_dismissed",
    ),
    "geo_action": (
        "no_action_totality_resolves", "propose_edd_rfi",
        "propose_withdrawal_only_restriction",
        "propose_trade_and_withdrawal_block",
        "propose_full_block_and_escalate",
    ),
}


class DecisionRecord(BaseModel):
    """One bounded decision: what was decided, why, and on what evidence.

    ``rationale`` is the audit-exact technical wording; ``plain_language`` is
    the same decision in compliance-officer terms. Both are deterministic
    functions of the same evidence values.
    """

    decision_id: str
    outcome: str
    rationale: str
    plain_language: str
    evidence: dict
    # Row-level pointers behind the rule's inputs, as audit-style citation
    # strings — populated where the input IS a row property (discovered
    # accounts, advisory match rows, contradicted-claim rows, the subject
    # row). Aggregate-input decisions (a rubric coverage, a hop cap) carry []
    # and their derivation is cited via the aggregates' own audit stamps —
    # per-decision semantics published in docs/agency-methodology.md.
    provenance: list[str] = []

    def summary(self) -> dict:
        return self.model_dump()


class SubjectRequest(BaseModel):
    """One complete, individually-usable routine ask (subject-facing text).

    ``text`` is the fully rendered request that could be put to the subject;
    ``citations`` are analyst-facing provenance pointers and are NEVER part of
    the text. Every ``text`` has passed :func:`assert_no_tipping_off`.
    """

    kind: str  # "transactions" | "corporate_records" | "prior_response"
    text: str
    citations: list[str]


class FollowUpQuestion(BaseModel):
    """The prepared follow-up material for one contradicted claim.

    ``requests`` are discrete standalone asks — a worklist for the human
    analyst, not a pre-assembled letter. ``sources`` records which evidence
    surfaces rebutted the claim (analyst metadata; device-sourced legs never
    generate a subject-facing request). ``suppressed`` names any request kind
    the fail-closed validator refused to emit (flagged for human authoring).
    """

    claim_id: str
    sources: list[str]
    requests: list[SubjectRequest]
    suppressed: list[str] = []


class RfiFollowUp(BaseModel):
    """Follow-up RFI material — prepared for the human investigator, never sent."""

    rfi_id: str
    questions: list[FollowUpQuestion]


def agency_config() -> dict:
    """The full, versioned decision policy — every threshold and boundary
    behind the bounded decision points, including the follow-up disclosure
    policy. Single source of truth: stamped into the audit trail and
    regression-tested against the published methodology doc.
    """
    return {
        "version": AGENCY_VERSION,
        "decision_points": {k: list(v) for k, v in DECISION_OUTCOMES.items()},
        "thresholds": {
            "expand_min_new_accounts": EXPAND_MIN_NEW_ACCOUNTS,
            "second_advisory_min_matches": SECOND_ADVISORY_MIN_MATCHES,
            "re_rfi_min_contradicted": RE_RFI_MIN_CONTRADICTED,
            "sufficiency_min_events": SUFFICIENCY_MIN_EVENTS,
        },
        "sar_bar_rule": (
            "delegates to the Critic: clears_bar iff the bounded revision loop "
            "converged (Critique.meets_bar at the critic_config threshold)"
        ),
        "corroboration_rule": (
            "compares a name/variant-matched customer's KYC identity attributes "
            "against the designation's published identifiers, per hard field "
            "(date of birth, nationality, document number): corroborated_true_hit "
            "iff the document number matches or both date of birth and "
            "nationality match; name_only_dismissed iff two or more hard "
            "identifiers actively mismatch (a provably different person, reason "
            "recorded); otherwise possible_match_needs_human. An absent field on "
            "either side is UNKNOWN, never a mismatch. Recorded into the "
            "remediation-sweep chain; it drives review triage, not control flow"
        ),
        "geo_action_rule": (
            "the seventh decision point, in the remediation sweep, for a "
            "TERRITORY designation: each surfaced account's geo totality dossier "
            "is scored into a net presence score N = the sum of its signal "
            "weights (by weight class) minus the sum of its counter-evidence "
            "subtractions (by staleness status). Document staleness only degrades "
            "the subtraction; it never adds to N (expiry is never read as "
            "presence), and VPN markers are never scored. N is mapped to a "
            "proposal by band (see geo_action_bands): a rebutted signal "
            "(N<=0) proposes no action but the account still surfaces for human "
            "review with its full dossier; a single ordinary signal proposes an "
            "enhanced-due-diligence RFI (the honest ask when the totality cannot "
            "resolve); stronger totalities propose a withdrawal-only restriction, "
            "then a trade-and-withdrawal block, then a full block and escalation. "
            "Every outcome is a REVIEW-tier PROPOSAL for a human — nothing is "
            "executed. Like corroboration it is recorded, not routed"
        ),
        "geo_action_weights": {
            "signal_weights": dict(GEO_SIGNAL_WEIGHTS),
            "counter_weights": dict(GEO_COUNTER_WEIGHTS),
        },
        "geo_action_bands": (
            [{"outcome": outcome, "net_at_most": upper}
             for upper, outcome in GEO_ACTION_BANDS]
            + [{"outcome": GEO_ACTION_TOP, "net_at_most": None}]
        ),
        "decision_provenance": (
            "each stamped decision carries row-level citations where its "
            "inputs are row properties (expand_hop: accounts discovered last "
            "hop; second_advisory: the matches' evidence rows; re_rfi: the "
            "contradicted claims' assertion+rebuttal rows; sufficiency: the "
            "subject account row); aggregate-input decisions (sar_bar, and "
            "cap/frontier stops) carry none and are covered by the "
            "aggregates' own audit stamps"
        ),
        "boundaries": {
            "second_advisory": (
                "surfaced to the analyst only; the SAR drafter consumes the "
                "primary match alone"
            ),
            "re_rfi": (
                "discrete routine requests are prepared for the human "
                "investigator, who owns assembly and sending; the agent never "
                "sends anything"
            ),
            "insufficient_evidence": (
                "the case is referred to a human; no draft is attempted and "
                "nothing is fabricated"
            ),
        },
        "followup_disclosure": {
            "may_cite": [
                "routine corporate documentation requests",
                "the subject's own prior responses",
                "the subject's own transaction records",
            ],
            "never_reveal": [
                "device or session linkage",
                "evidence surfaces or internal analysis methods",
                "typology, suspicion, or reporting status",
                "wallet attribution or tracing focus",
            ],
            "validator": (
                "assert_no_tipping_off: fail-closed on every rendered "
                "subject-facing request; a failing request is suppressed and "
                "flagged for human authoring, never emitted"
            ),
        },
    }


# --- The five decision rules -------------------------------------------------


def decide_expand(hops_done: int, cap: int, new_accounts_last_hop: int, *,
                  provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Expand another hop? Continue while the frontier stays productive.

    A hop whose previous hop discovered no new accounts would start from an
    empty frontier and add nothing, so ``stop_frontier_exhausted`` is provably
    identical in output to walking on to the cap.
    """
    evidence = {"hops_done": hops_done, "cap": cap,
                "new_accounts_last_hop": new_accounts_last_hop}
    if hops_done >= cap:
        outcome = "stop_cap"
        rationale = (f"hop cap reached ({hops_done}/{cap}); expansion stops at "
                     "the configured bound")
        plain = (f"The network review reached its configured maximum reach "
                 f"({cap} step(s) from the subject); policy stops it there to "
                 "keep review scope bounded.")
    elif new_accounts_last_hop >= EXPAND_MIN_NEW_ACCOUNTS:
        outcome = "continue"
        rationale = (f"hop {hops_done} discovered {new_accounts_last_hop} new "
                     f"account(s); the frontier is productive, so one more hop "
                     f"is proposed ({hops_done + 1}/{cap})")
        plain = (f"Found {new_accounts_last_hop} more connected account(s) one "
                 "link away (transaction counterparties, shared devices, or "
                 "shared KYC documents), so the network review widens by one "
                 "more step.")
    else:
        outcome = "stop_frontier_exhausted"
        rationale = (f"hop {hops_done} discovered no new accounts; the frontier "
                     "is exhausted and a further hop would be a no-op")
        plain = ("No further connected accounts found; the subject's network "
                 "is fully mapped within the review scope.")
    return DecisionRecord(decision_id="expand_hop", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


def decide_second_advisory(matches: Sequence[AdvisoryMatch], *,
                           provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Pull a second advisory? Only when more than one corroborated match
    survived the corroboration gate; the runner-up is surfaced, never drafted.
    """
    ids = [m.advisory_id for m in matches]
    evidence = {"corroborated_matches": len(matches), "advisory_ids": ids}
    if len(matches) >= SECOND_ADVISORY_MIN_MATCHES:
        outcome = "pull_second"
        rationale = (f"{len(matches)} corroborated advisories matched; the "
                     f"runner-up ({ids[1]}) is surfaced for analyst review "
                     f"alongside the primary ({ids[0]}); the SAR draft consumes "
                     "only the primary")
        plain = (f"The case facts matched more than one FinCEN advisory. The "
                 f"strongest match ({ids[0]}) anchors the SAR narrative; the "
                 f"runner-up ({ids[1]}) is shown for analyst awareness only "
                 "and never enters the draft.")
    elif len(matches) == 1:
        outcome = "single_match"
        rationale = (f"one corroborated advisory matched ({ids[0]}); nothing "
                     "further to surface")
        plain = (f"Exactly one FinCEN advisory ({ids[0]}) matched the case "
                 "facts with corroborating case evidence; it anchors the SAR "
                 "narrative.")
    else:
        outcome = "no_match"
        rationale = "no corroborated advisory matched; nothing to surface"
        plain = ("No FinCEN advisory matched the case facts with "
                 "corroborating case evidence.")
    return DecisionRecord(decision_id="second_advisory", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


def decide_re_rfi(table: Optional[ContradictionTable], *,
                  provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Re-RFI? Recommended only when the adjudicated table holds at least one
    ``contradicted`` claim — the sole flag verdict. Prepared, never sent.

    The existing rationale wording is already plain-clear (PM-reviewed), so
    ``plain_language`` mirrors it.
    """
    if table is None:
        rationale = "no RFI on file for this subject; nothing to follow up"
        return DecisionRecord(
            decision_id="re_rfi", outcome="not_applicable",
            rationale=rationale, plain_language=rationale,
            evidence={"rfi_id": None, "contradicted_claims": 0},
            provenance=list(provenance or []),
        )
    contradicted = table.contradictions
    evidence = {"rfi_id": table.rfi_id,
                "contradicted_claims": len(contradicted),
                "claim_ids": [a.claim_id for a in contradicted]}
    if len(contradicted) >= RE_RFI_MIN_CONTRADICTED:
        outcome = "recommend_re_rfi"
        rationale = (f"{len(contradicted)} claim(s) in {table.rfi_id} "
                     "adjudicated contradicted; a follow-up RFI is drafted and "
                     "proposed to the human investigator (never sent)")
    else:
        outcome = "no_contradictions"
        rationale = (f"no claim in {table.rfi_id} was adjudicated contradicted; "
                     "no follow-up is proposed")
    return DecisionRecord(decision_id="re_rfi", outcome=outcome,
                          rationale=rationale, plain_language=rationale,
                          evidence=evidence, provenance=list(provenance or []))


def decide_sufficiency(subject_resolved: bool, event_count: int, *,
                       provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Evidence sufficient to draft? The minimum for a fail-closed draft
    attempt is a resolved subject and one grounded timeline event ("who" and
    "when" are citable). Below that, the case is referred to a human — the
    drafter never runs on evidence that cannot ground its own narrative.
    """
    evidence = {"subject_resolved": subject_resolved, "event_count": event_count}
    if subject_resolved and event_count >= SUFFICIENCY_MIN_EVENTS:
        outcome = "sufficient"
        rationale = (f"subject resolved with {event_count} grounded timeline "
                     "event(s); who and when are citable, so a fail-closed "
                     "draft attempt proceeds")
        plain = (f"The case holds enough verified source records "
                 f"({event_count} dated events for a confirmed subject) to "
                 "draft a narrative in which every sentence cites its source.")
    else:
        outcome = "insufficient"
        rationale = ("the evidence cannot ground a citable narrative (subject "
                     f"resolved: {subject_resolved}, events: {event_count}); "
                     "the case is flagged for human referral and no draft is "
                     "attempted")
        plain = ("Too few verifiable source records to draft from; the case "
                 "goes to an investigator rather than risking an unsupported "
                 "narrative.")
    return DecisionRecord(decision_id="sufficiency", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


def decide_sar_bar(history: CritiqueHistory, *,
                   provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Does the SAR clear the bar? Delegates to the Critic's rubric verdict:
    the draft clears only if the bounded revision loop converged. Either way a
    human reviews and decides — this records the disposition, it does not file.
    """
    final = history.final
    evidence = {"converged": history.converged,
                "coverage": round(final.coverage, 3),
                "flagged": list(history.flagged)}
    if history.converged:
        outcome = "clears_bar"
        rationale = (f"the Critic's rubric bar is met (coverage "
                     f"{round(final.coverage, 3)}); the draft proceeds to "
                     "packaging for human review")
        plain = rationale  # PM-reviewed as already clear
    else:
        outcome = "human_review"
        rationale = (f"rubric coverage {round(final.coverage, 3)} with unmet "
                     f"element(s) {sorted(history.flagged)}; the draft is "
                     "flagged for human review (gaps are never fabricated)")
        plain = ("The draft does not yet cover every element FinCEN expects "
                 f"in a SAR narrative (missing: {', '.join(sorted(history.flagged))}); "
                 "it is routed to an investigator to complete, and gaps are "
                 "never invented.")
    return DecisionRecord(decision_id="sar_bar", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


# --- Corroboration (Part II): identity match vs published identifiers ---------

# The hard identifiers compared, in the order they appear in a recorded reason.
# ``doc_number`` is decisive on its own (a shared government document number is
# a strong unique-identity signal); ``dob`` + ``nationality`` corroborate
# jointly. Ordered so the recorded rationale reads the same way every time.
_CORROBORATION_FIELDS: tuple[tuple[str, str], ...] = (
    ("dob", "date of birth"),
    ("nationality", "nationality"),
    ("doc_number", "document number"),
)


def _cmp_identifier(a: Optional[str], b: Optional[str]) -> str:
    """Compare one identifier field: ``match`` / ``mismatch`` / ``unknown``.

    ``unknown`` iff either side is absent — an identifier the list never
    published (a name-only listing) can neither confirm nor disqualify, so it is
    never read as a mismatch. Case-insensitive, whitespace-trimmed."""
    x = (a or "").strip().lower()
    y = (b or "").strip().lower()
    if not x or not y:
        return "unknown"
    return "match" if x == y else "mismatch"


def decide_corroboration(candidate_uid: int, designated_name: str,
                         kyc: dict, identifiers: dict, *,
                         provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Corroborate a name/variant-matched customer against a designation's
    published identifiers — the step that separates a true hit from a same-name
    collision. A name match alone is never enough to assert identity; this
    decision proposes one of three review dispositions and, on a dismissal,
    records exactly which identifiers disqualified the match.

    Pure over its inputs (``kyc`` and ``identifiers`` are ``{dob, nationality,
    doc_type, doc_number}`` maps): no row, id, or ground-truth label is read.
    The disposition is a *proposal for human review*, never an assertion of
    identity — every branch stays REVIEW-tier.
    """
    cmp = {field: _cmp_identifier(kyc.get(field), identifiers.get(field))
           for field, _ in _CORROBORATION_FIELDS}
    matched = [label for field, label in _CORROBORATION_FIELDS if cmp[field] == "match"]
    mismatched = [label for field, label in _CORROBORATION_FIELDS if cmp[field] == "mismatch"]
    evidence = {
        "candidate_uid": candidate_uid,
        "designated_name": designated_name,
        "field_comparison": dict(cmp),
        "matched_fields": matched,
        "mismatched_fields": mismatched,
    }

    if cmp["doc_number"] == "match" or (cmp["dob"] == "match" and cmp["nationality"] == "match"):
        outcome = "corroborated_true_hit"
        basis = ("the document number matches" if cmp["doc_number"] == "match"
                 else "date of birth and nationality both match")
        rationale = (f"KYC identity attributes corroborate the name match to "
                     f"{designated_name!r}: {basis} ({', '.join(matched)}); "
                     "proposed as a corroborated hit for human confirmation")
        plain = (f"The customer's identity documents line up with the "
                 f"designated party's published details ({basis}); this is "
                 "surfaced as a likely true match for an officer to confirm.")
    elif len(mismatched) >= 2:
        outcome = "name_only_dismissed"
        rationale = (f"name match to {designated_name!r} is not corroborated: "
                     f"{', '.join(mismatched)} each differ from the designated "
                     "party's published identifiers — a same-name collision; "
                     "dismissed with the mismatch recorded for review")
        plain = (f"The customer shares the designated party's name but is a "
                 f"different person — {', '.join(mismatched)} do not match the "
                 "published details; dismissed as a name-only collision, with "
                 "the reason on record.")
    else:
        outcome = "possible_match_needs_human"
        rationale = (f"name match to {designated_name!r} is partially "
                     f"corroborated (matched: {matched or 'none'}; the list "
                     "published no disqualifying identifier); neither confirmed "
                     "nor dismissible, so it is routed to a human to resolve")
        plain = ("The customer's name matches but the available identity "
                 "details neither confirm nor rule out the designated party; "
                 "routed to an officer to resolve.")
    return DecisionRecord(decision_id="corroboration", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


# --- geo_action (Part III): totality dossier -> a REVIEW-tier proposal ---------


def _geo_band(net: int) -> str:
    """Map a net presence score to a proposal — the first band whose inclusive
    upper bound the score does not exceed, else the top (unbounded) outcome.
    Shares :data:`GEO_ACTION_BANDS` with the config stamp so the two cannot
    drift."""
    for upper, outcome in GEO_ACTION_BANDS:
        if net <= upper:
            return outcome
    return GEO_ACTION_TOP


def decide_geo_action(uid: int,
                      signal_weight_classes: Sequence[str],
                      counter_statuses: Sequence[str], *,
                      provenance: Optional[list[str]] = None) -> DecisionRecord:
    """Propose a remediation action for one surfaced geo dossier — the seventh
    decision point, in the remediation sweep, for a TERRITORY designation.

    Pure over its inputs. ``signal_weight_classes`` is the weight class of each
    positive location signal the dossier collected (``high_value`` / ``standard``
    / ``weak``); ``counter_statuses`` is the staleness status of each piece of
    counter-evidence (``valid`` / ``expired``; a ``missing`` refresh is a control
    gap, never counter-evidence, and so never appears here). The caller (the U2b
    wiring) reads them off the :class:`~okojo.geo.GeoDossier`; this function never
    touches the store, a row, or a ground-truth label.

    The net presence score ``N`` = sum of signal weights − sum of counter
    subtractions. Staleness only *degrades* the subtraction (``expired`` → 1 vs
    ``valid`` → 3); expiry is never read as presence, so it never adds to ``N``,
    and VPN markers are never scored. ``N`` maps to one of five REVIEW-tier
    proposals by band (see :data:`GEO_ACTION_BANDS`). A rebutted signal
    (``no_action_totality_resolves``) proposes nothing, but the account is still
    surfaced for a human with its full dossier — a resolved review, never a
    silent dismissal. Every outcome is a proposal; nothing is executed.
    """
    signal_score = sum(GEO_SIGNAL_WEIGHTS[c] for c in signal_weight_classes)
    counter_sub = sum(GEO_COUNTER_WEIGHTS[s] for s in counter_statuses)
    net = signal_score - counter_sub
    outcome = _geo_band(net)

    evidence = {
        "uid": uid,
        "signal_weight_classes": list(signal_weight_classes),
        "counter_statuses": list(counter_statuses),
        "signal_score": signal_score,
        "counter_subtraction": counter_sub,
        "net_presence_score": net,
    }

    n_sig = len(signal_weight_classes)
    score_expr = (f"net presence score {net} (signals {signal_score} "
                  f"− counter-evidence {counter_sub})")
    if outcome == "no_action_totality_resolves":
        rationale = (f"{score_expr}: the location signal(s) are rebutted by "
                     "valid counter-evidence; no restriction is proposed, but "
                     "the account remains surfaced for human review with its "
                     "full dossier (a resolved review, not a dismissal)")
        plain = ("A possible-location signal fired but current, valid "
                 "documentation argues the customer is resident elsewhere, so "
                 "no restriction is proposed — the account is still shown to a "
                 "reviewer with everything on file.")
    elif outcome == "propose_edd_rfi":
        rationale = (f"{score_expr}: the totality is present but cannot resolve; "
                     "an enhanced-due-diligence identity/geography RFI is "
                     "proposed as the honest ask (drafted for a human, never "
                     "sent)")
        plain = ("There is a location signal but not enough to act on; the "
                 "proposal is to ask the customer for enhanced identity and "
                 "residency details — prepared for an officer, never sent "
                 "automatically.")
    elif outcome == "propose_withdrawal_only_restriction":
        rationale = (f"{score_expr}: a clear location indication; a "
                     "withdrawal-only restriction is proposed for human action")
        plain = ("A clear indication of possible presence in the sanctioned "
                 "territory; the proposal for a reviewer is to restrict the "
                 "account to withdrawals only while it is investigated.")
    elif outcome == "propose_trade_and_withdrawal_block":
        rationale = (f"{score_expr}: a strong, corroborated location totality; a "
                     "trade-and-withdrawal block is proposed for human action")
        plain = ("Several independent signals corroborate possible presence; "
                 "the proposal for a reviewer is to block both trading and "
                 "withdrawals pending resolution.")
    else:  # propose_full_block_and_escalate
        rationale = (f"{score_expr}: an overwhelming, multi-signal resident "
                     "profile; a full block and escalation is proposed for human "
                     "action")
        plain = ("The account matches the territory on many independent "
                 "signals at once; the proposal for a reviewer is a full block "
                 "and escalation.")
    rationale = f"{rationale} [{n_sig} signal(s)]"

    return DecisionRecord(decision_id="geo_action", outcome=outcome,
                          rationale=rationale, plain_language=plain,
                          evidence=evidence, provenance=list(provenance or []))


# --- Anti-tipping-off validator (subject-facing text only) -------------------


class TippingOffRisk(ValueError):
    """Raised when text meant for a subject's eyes could tip them off that
    their activity is under review, or reveal evidence surfaces / methods."""


# Two banned sets, case-insensitive, stem/word-boundary based. Calibrated so
# the approved neutral templates PASS: "periodic review", "file",
# "verification", "register of directors", and "group structure" are all
# legitimate administrative vocabulary — the bans target "under review" as a
# phrase, "structured/structuring" exactly (not "structure"), and whole words
# for the acronyms.
_TIPPING_OFF_PATTERNS: tuple[tuple[str, str], ...] = (
    # (a) tipping-off vocabulary: review/reporting status must never leak
    ("sar", r"\bsar\b"),
    ("str", r"\bstr\b"),
    ("suspicious", r"\bsuspici"),
    ("report", r"\breport(ed|ing|s)?\b"),
    ("laundering", r"\blaunder"),
    ("aml", r"\baml\b"),
    ("fiu", r"\bfiu\b"),
    ("financial-intelligence", r"\bfinancial intelligence\b"),
    ("sanctions", r"\bsanction"),
    ("ofac", r"\bofac\b"),
    ("investigation", r"\binvestigat"),
    ("compliance", r"\bcomplianc"),
    ("flag", r"\bflag"),
    ("alert", r"\balert"),
    ("frozen", r"\bfrozen\b"),
    ("blocked", r"\bblocked\b"),
    ("law-enforcement", r"\blaw enforcement\b"),
    ("police", r"\bpolice\b"),
    ("central-bank", r"\bcentral bank\b"),
    ("regulator", r"\bregulator"),
    ("under-review", r"\bunder review\b"),
    # (b) tradecraft / method / evidence-surface vocabulary
    ("onchain", r"\bon-?chain\b"),
    ("registry", r"\bregistry\b"),
    ("prior-rfi-surface", r"\bprior_rfi\b"),
    ("device", r"\bdevice"),
    ("fingerprint", r"\bfingerprint"),
    ("inconsistent", r"\binconsistent"),
    ("contradict", r"\bcontradict"),
    ("structuring", r"\bstructured\b|\bstructuring\b"),
    ("layering", r"\blayering\b"),
    ("gas-funding", r"\bgas\b"),
    ("shell", r"\bshell\b"),
    ("typology", r"\btypolog"),
    ("iran", r"\biran"),
    ("smuggling", r"\bsmuggl"),
    ("wallet", r"\bwallet"),
    ("advisory-id", r"\bfin-\d{4}-\w+\b"),
)
_COMPILED_BANS = tuple(
    (label, re.compile(pattern)) for label, pattern in _TIPPING_OFF_PATTERNS
)


def assert_no_tipping_off(text: str) -> None:
    """Fail-closed guard for SUBJECT-FACING text only.

    Run on the FULLY RENDERED request (after any interpolation — interpolated
    values are the likeliest smuggling path). Internal artifacts (the SAR
    narrative, the case package, decision rationales) legitimately use this
    vocabulary and must NOT be passed through this check.
    """
    low = text.lower()
    hits = sorted({label for label, pat in _COMPILED_BANS if pat.search(low)})
    if hits:
        raise TippingOffRisk(
            "subject-facing text failed the anti-tipping-off check "
            f"(banned terms: {', '.join(hits)})"
        )


# --- Follow-up request drafting (discrete routine asks, never a letter) ------

# Approved neutral templates. Each is a complete, individually-usable routine
# ask built from administrative lead-ins only — safe by construction, and
# still validated after rendering (defense in depth).
_TX_REQUEST = (
    "As part of a periodic review of your file, please identify the "
    "counterparty and commercial purpose of the following transactions: "
    "{tx_ids}, and provide supporting settlement documentation (contracts, "
    "invoices, bills of lading)."
)
_CORPORATE_RECORDS_REQUEST = (
    "As part of a periodic review of your corporate records, please provide: "
    "(i) a current register of directors and officers; (ii) an up-to-date "
    "group structure or organizational chart identifying any parent, "
    "subsidiary, and affiliated entities, together with their beneficial "
    "ownership; and (iii) copies of any management, service, agency, or "
    "intercompany agreements to which your organization is a party."
)
_PRIOR_RESPONSE_REQUEST = (
    "In your response to {prior_rfi_id}, {referenced} was referenced. Please "
    "provide a copy of that agreement and confirm whether it remains in "
    "effect."
)
_GENERIC_ARRANGEMENT = "an arrangement bearing on this matter"

# A quotable "...agreement/arrangement" phrase from the subject's own words,
# used only when EXACTLY one clean match exists; anything less than clean
# falls back to the generic phrase (PM rule).
_ARRANGEMENT_RE = re.compile(r"\ban? [a-z][a-z \-]{2,50}? (?:agreement|arrangement)\b")


def _referenced_arrangement(statement: str) -> str:
    matches = [m.group(0) for m in _ARRANGEMENT_RE.finditer(statement.lower())]
    if len(matches) == 1:
        return matches[0]
    return _GENERIC_ARRANGEMENT


def _admit(requests: list[SubjectRequest], suppressed: list[str],
           kind: str, text: str, citations: list[str]) -> None:
    """Fail-closed admission: a request that trips the validator is suppressed
    and flagged for human authoring — never emitted."""
    try:
        assert_no_tipping_off(text)
    except TippingOffRisk:
        suppressed.append(kind)
        return
    requests.append(SubjectRequest(kind=kind, text=text, citations=citations))


def draft_followup(table: ContradictionTable) -> RfiFollowUp:
    """Prepare discrete, standalone routine requests per contradicted claim.

    NOT a pre-assembled letter: each request is individually usable, and the
    human analyst owns ordering, assembly, and sending. Per disclosable
    evidence leg:

    * on-chain  -> cite the subject's OWN transaction rows only (rows whose
      provenance source is ``transactions``; gas-funding and address-
      attribution rows are excluded — citing them would reveal tracing focus);
    * registry  -> a routine corporate-documentation ask that deliberately
      does NOT name the denied entity, so the subject's inclusion or omission
      of the relevant agreement is itself informative;
    * prior RFI -> quote the subject's own earlier response by reference id;
    * device    -> NO subject-facing request, ever (internal linkage
      capability is never hinted at; the leg stays in the SAR and the
      contradiction table).

    Every rendered request must pass :func:`assert_no_tipping_off`; a failing
    request is suppressed and flagged for human authoring.
    """
    questions = []
    for adj in table.contradictions:
        by_source: dict[str, list] = {}
        for r in adj.rebuttals:
            by_source.setdefault(r.source, []).append(r)

        requests: list[SubjectRequest] = []
        suppressed: list[str] = []

        # on-chain -> the subject's own transaction rows only
        onchain = by_source.get("onchain", [])
        tx_ids = sorted({
            p.row_key for r in onchain for p in r.provenance
            if p.source == "transactions"
        })
        if tx_ids:
            _admit(requests, suppressed, kind="transactions",
                   text=_TX_REQUEST.format(tx_ids=", ".join(tx_ids)),
                   citations=[r.cite() for r in onchain])

        # registry -> neutral corporate-documentation ask (no entity named)
        registry = by_source.get("registry", [])
        if registry:
            _admit(requests, suppressed, kind="corporate_records",
                   text=_CORPORATE_RECORDS_REQUEST,
                   citations=[r.cite() for r in registry])

        # prior RFI -> quote the subject's own earlier response
        for r in by_source.get("prior_rfi", []):
            prior_id = next(
                (p.row_key for p in r.provenance if p.source == "rfi_prior"),
                r.provenance[0].row_key if r.provenance else "your earlier response",
            )
            referenced = _referenced_arrangement(r.statement)
            text = _PRIOR_RESPONSE_REQUEST.format(
                prior_rfi_id=prior_id, referenced=referenced)
            if referenced != _GENERIC_ARRANGEMENT:
                # an extracted phrase is the likeliest smuggling path — fall
                # back to the generic phrase before the fail-closed admission
                try:
                    assert_no_tipping_off(text)
                except TippingOffRisk:
                    text = _PRIOR_RESPONSE_REQUEST.format(
                        prior_rfi_id=prior_id, referenced=_GENERIC_ARRANGEMENT)
            _admit(requests, suppressed, kind="prior_response",
                   text=text, citations=[r.cite()])

        # device -> policy-excluded: no subject-facing request, ever

        questions.append(FollowUpQuestion(
            claim_id=adj.claim_id, sources=adj.sources,
            requests=requests, suppressed=suppressed,
        ))
    return RfiFollowUp(rfi_id=table.rfi_id, questions=questions)
