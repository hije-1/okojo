"""Unit tests for the identity-review RFI drafter (Part II T5a).

The eval (``test_identity_rfi_eval.py``) proves the scenario disposition; these
prove the drafter's CONTRACT directly on constructed inputs: the approved
template is anti-tipping-off-clean, only the unresolved outcome triggers a draft,
grounding is fail-closed, and every failure is suppressed-and-surfaced (never
silently dropped, never emitted).
"""

from __future__ import annotations

import pytest

from okojo.agency import DecisionRecord, TippingOffRisk, assert_no_tipping_off
from okojo.sweep import designation_from_record
from okojo.sweep import identity_rfi as mod
from okojo.sweep.identity_rfi import (
    DRAFT_STATUS,
    draft_identity_review_rfis,
)


def _decision(uid: int, outcome: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=f"corroboration:{uid}",
        outcome=outcome,
        rationale="test",
        plain_language="test",
        evidence={"candidate_uid": uid},
        provenance=[],
    )


@pytest.fixture()
def designation(conn):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    return designation_from_record(recs["DES-2026-0006"])


def test_template_is_tipping_off_clean():
    """The approved template, rendered with a benign subject name, reveals no
    match/method/list/interest — it passes the subject-facing guard as written."""
    text = mod._IDENTITY_REVIEW_REQUEST.format(subject_name="Jordan Rivera")
    assert_no_tipping_off(text)  # does not raise
    low = text.lower()
    for banned in ("designation", "sanction", "screen", "match", "list",
                   "review", "report", "registry", "investigat"):
        assert banned not in low


def test_possible_match_drafts_grounded_rfi(conn, designation):
    """The unresolved candidate (a real KYC row) earns one grounded draft."""
    uid = 500000026
    drafts, suppressed = draft_identity_review_rfis(
        conn, designation, [_decision(uid, "possible_match_needs_human")])
    assert suppressed == []
    assert len(drafts) == 1
    r = drafts[0]
    assert r.uid == uid
    assert r.status == DRAFT_STATUS
    assert r.rfi_id == "IDR-DES-2026-0006-0001"
    kyc = conn.kyc_identity_attributes_for(uid)
    assert r.citations == [kyc.provenance.cite()]
    assert r.provenance == [kyc.provenance]
    assert r.subject_name in r.text
    assert_no_tipping_off(r.text)


def test_only_possible_match_triggers(conn, designation):
    """A true hit and a dismissal earn no request; only the unresolved outcome
    does. Numbering counts only emitted drafts (deterministic ids)."""
    corroboration = [
        _decision(500000024, "corroborated_true_hit"),
        _decision(500000028, "name_only_dismissed"),
        _decision(500000026, "possible_match_needs_human"),
    ]
    drafts, suppressed = draft_identity_review_rfis(conn, designation, corroboration)
    assert [r.uid for r in drafts] == [500000026]
    assert drafts[0].rfi_id == "IDR-DES-2026-0006-0001"
    assert suppressed == []


def test_no_candidates_is_empty(conn, designation):
    drafts, suppressed = draft_identity_review_rfis(conn, designation, [])
    assert drafts == [] and suppressed == []


def test_unresolvable_kyc_is_suppressed_and_surfaced(conn, designation):
    """A candidate with no KYC identity row cannot be grounded — the draft is
    suppressed and surfaced with a reason, never emitted."""
    drafts, suppressed = draft_identity_review_rfis(
        conn, designation, [_decision(999999999, "possible_match_needs_human")])
    assert drafts == []
    assert len(suppressed) == 1
    assert suppressed[0].uid == 999999999
    assert "ground" in suppressed[0].reason.lower()


def test_tipping_off_failure_is_suppressed_and_surfaced(conn, designation, monkeypatch):
    """If the rendered text were ever to trip the anti-tipping-off guard, the
    draft is suppressed-and-surfaced — proven by injecting a banned term into the
    template and confirming the fail-closed path (no draft escapes)."""
    poisoned = mod._IDENTITY_REVIEW_REQUEST + "\n\n(sanctions screening reference)"
    monkeypatch.setattr(mod, "_IDENTITY_REVIEW_REQUEST", poisoned)
    drafts, suppressed = draft_identity_review_rfis(
        conn, designation, [_decision(500000026, "possible_match_needs_human")])
    assert drafts == []
    assert len(suppressed) == 1
    assert suppressed[0].uid == 500000026
    assert "tipping-off" in suppressed[0].reason.lower()
    # Sanity: the poisoned text really would have tripped the guard.
    with pytest.raises(TippingOffRisk):
        assert_no_tipping_off(poisoned.format(subject_name="X"))
