"""Bounded agentic decision points (Phase 6).

Each decision is a PURE function of the evidence state: same evidence, same
outcome, every time. "Agency" here means rule-based, bounded, auditable
branching — never stochastic or model-driven wandering. Every rule below:

* takes only explicit evidence arguments (never the graph state, never a
  ground-truth label, never a claim/subject id);
* returns a :class:`DecisionRecord` whose ``rationale`` says why in calibrated
  language (proposes / surfaces / recommends / flags — a human always decides);
* is stamped into the tamper-evident audit chain by the orchestrator, with the
  driving evidence, so the full decision trace is reproducible and reviewable.

The thresholds are tunable policy parameters, not constants of nature; they are
published (with rationale) in ``docs/agency-methodology.md``, exposed through
:func:`agency_config`, stamped into the audit trail once per run, and
regression-tested against the doc so code and public methodology cannot drift.

Hard boundaries (also published in the methodology doc):

* a second advisory match is *surfaced to the analyst only* — the SAR drafter
  consumes the primary match alone;
* a follow-up RFI is *drafted and proposed, never sent*;
* an insufficient-evidence case is *referred to a human* — no draft is
  attempted and nothing is fabricated.
"""

from __future__ import annotations

from typing import Optional, Sequence

from pydantic import BaseModel

from ..advisory import AdvisoryMatch
from ..rfi import ContradictionTable
from ..sar import CritiqueHistory

# Bump on any change to a threshold, outcome set, or decision rule. Stamped
# into the audit trail and mirrored by the published methodology doc.
AGENCY_VERSION = "1.0.0"

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
    """One bounded decision: what was decided, why, and on what evidence."""

    decision_id: str
    outcome: str
    rationale: str
    evidence: dict

    def summary(self) -> dict:
        return self.model_dump()


class FollowUpQuestion(BaseModel):
    """One proposed follow-up question, tied to a contradicted claim."""

    claim_id: str
    question: str
    sources: list[str]
    citations: list[str]


class RfiFollowUp(BaseModel):
    """A drafted follow-up RFI — proposed to the human investigator, never sent."""

    rfi_id: str
    questions: list[FollowUpQuestion]


def agency_config() -> dict:
    """The full, versioned decision policy — every threshold and boundary
    behind the bounded decision points. Single source of truth: stamped into
    the audit trail and regression-tested against the published methodology
    doc.
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
                "a follow-up RFI is drafted and proposed, never sent; a human "
                "decides"
            ),
            "insufficient_evidence": (
                "the case is referred to a human; no draft is attempted and "
                "nothing is fabricated"
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
    elif new_accounts_last_hop >= EXPAND_MIN_NEW_ACCOUNTS:
        outcome = "continue"
        rationale = (f"hop {hops_done} discovered {new_accounts_last_hop} new "
                     f"account(s); the frontier is productive, so one more hop "
                     f"is proposed ({hops_done + 1}/{cap})")
    else:
        outcome = "stop_frontier_exhausted"
        rationale = (f"hop {hops_done} discovered no new accounts; the frontier "
                     "is exhausted and a further hop would be a no-op")
    return DecisionRecord(decision_id="expand_hop", outcome=outcome,
                          rationale=rationale, evidence=evidence)


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
    elif len(matches) == 1:
        outcome = "single_match"
        rationale = (f"one corroborated advisory matched ({ids[0]}); nothing "
                     "further to surface")
    else:
        outcome = "no_match"
        rationale = "no corroborated advisory matched; nothing to surface"
    return DecisionRecord(decision_id="second_advisory", outcome=outcome,
                          rationale=rationale, evidence=evidence)


def decide_re_rfi(table: Optional[ContradictionTable]) -> DecisionRecord:
    """Re-RFI? Recommended only when the adjudicated table holds at least one
    ``contradicted`` claim — the sole flag verdict. Drafted, never sent.
    """
    if table is None:
        return DecisionRecord(
            decision_id="re_rfi", outcome="not_applicable",
            rationale="no RFI on file for this subject; nothing to follow up",
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
                          rationale=rationale, evidence=evidence)


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
    else:
        outcome = "insufficient"
        rationale = ("the evidence cannot ground a citable narrative (subject "
                     f"resolved: {subject_resolved}, events: {event_count}); "
                     "the case is flagged for human referral and no draft is "
                     "attempted")
    return DecisionRecord(decision_id="sufficiency", outcome=outcome,
                          rationale=rationale, evidence=evidence)


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
    else:
        outcome = "human_review"
        rationale = (f"rubric coverage {round(final.coverage, 3)} with unmet "
                     f"element(s) {sorted(history.flagged)}; the draft is "
                     "flagged for human review (gaps are never fabricated)")
    return DecisionRecord(decision_id="sar_bar", outcome=outcome,
                          rationale=rationale, evidence=evidence)


def draft_followup(table: ContradictionTable) -> RfiFollowUp:
    """Draft one deterministic follow-up question per contradicted claim.

    Each question restates the subject's own assertion, names the evidence
    surfaces that rebut it, and carries the rebuttals' provenance citations —
    so the human investigator can send (or discard) it with both sides in
    hand.
    """
    questions = []
    for adj in table.contradictions:
        srcs = adj.sources
        question = (
            f'Your response stated: "{adj.claim_text}" Evidence on record '
            f"({', '.join(srcs)}) is inconsistent with this statement. Please "
            "provide documentation that addresses the cited records directly."
        )
        questions.append(FollowUpQuestion(
            claim_id=adj.claim_id, question=question, sources=srcs,
            citations=[r.cite() for r in adj.rebuttals],
        ))
    return RfiFollowUp(rfi_id=table.rfi_id, questions=questions)
