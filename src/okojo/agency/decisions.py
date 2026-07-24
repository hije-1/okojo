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
AGENCY_VERSION = "1.1.0"

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

# The five decision points and their closed outcome sets. The outcome strings
# double as LangGraph routing keys, so the branch taken is exactly the outcome
# recorded in the audit trail.
DECISION_OUTCOMES: dict[str, tuple[str, ...]] = {
    "expand_hop": ("continue", "stop_cap", "stop_frontier_exhausted"),
    "second_advisory": ("pull_second", "single_match", "no_match"),
    "re_rfi": ("recommend_re_rfi", "no_contradictions", "not_applicable"),
    "sufficiency": ("sufficient", "insufficient"),
    "sar_bar": ("clears_bar", "human_review"),
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


def decide_expand(hops_done: int, cap: int, new_accounts_last_hop: int) -> DecisionRecord:
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
                          evidence=evidence)


def decide_second_advisory(matches: Sequence[AdvisoryMatch]) -> DecisionRecord:
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
                          evidence=evidence)


def decide_re_rfi(table: Optional[ContradictionTable]) -> DecisionRecord:
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
                          evidence=evidence)


def decide_sufficiency(subject_resolved: bool, event_count: int) -> DecisionRecord:
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
                          evidence=evidence)


def decide_sar_bar(history: CritiqueHistory) -> DecisionRecord:
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
                          evidence=evidence)


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
