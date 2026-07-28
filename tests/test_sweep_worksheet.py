"""Phase 8 Slice C: the triage worksheet + drafted-never-sent escalations.

The full-equality discipline continues: expected action assignments are
asserted as a complete uid -> action mapping derived from persona roles, so an
extra or missing row trips the test as loudly as a wrong action.
"""

from __future__ import annotations

import pytest

from okojo.provenance import Provenance
from okojo.sar import BANNED_TERMS, UnresolvableCitationError
from okojo.sweep import (
    ACTION_VOCABULARY,
    DRAFT_STATUS,
    assert_worksheet_resolvable,
    draft_escalations,
    run_sweep,
)

_NO_HOPS_SENTINEL = 10**6


@pytest.fixture()
def live_result(conn, sweep_designations, tmp_path):
    live, _ = sweep_designations
    return run_sweep(live, out_dir=tmp_path / "ws", conn=conn)


# --------------------------------------------------------------------------- #
# worksheet content
# --------------------------------------------------------------------------- #
def test_worksheet_action_assignment_full_equality(live_result, ring):
    """The complete expected worksheet, uid -> action — never a subset check.

    Five exposed accounts with consistent no_hold get the hold-review
    proposal; the two exposed gap accounts get the gap flag; the tagged
    adjacent account gets the named tag flag; the two other adjacent accounts
    get the generic non-flow review flag. Nothing else appears."""
    expected = {
        ring["KINGPIN"]: "proposes_designation_hold_review",
        ring["SHELL_NZ"]: "proposes_designation_hold_review",
        ring["SHELL_AE"]: "proposes_designation_hold_review",
        ring["SHELL_HK"]: "proposes_designation_hold_review",
        ring["SHELL_CN"]: "proposes_designation_hold_review",
        ring["TRUST"]: "flags_reconciliation_gap",
        ring["SHELL_TR"]: "flags_reconciliation_gap",
        ring["PRIVILEGED"]: "flags_internal_tag_for_review",
        ring["EMPLOYEE"]: "flags_for_review_non_flow_linkage",
        ring["SIBLING"]: "flags_for_review_non_flow_linkage",
    }
    assert {r.uid: r.recommended_action for r in live_result.worksheet} == expected


def test_worksheet_triage_order_is_the_published_sort(live_result):
    ws = live_result.worksheet
    keys = [
        (ACTION_VOCABULARY.index(r.recommended_action), -r.exposure_usdt,
         r.hops if r.hops is not None else _NO_HOPS_SENTINEL, r.uid)
        for r in ws
    ]
    assert keys == sorted(keys), "worksheet must ship in triage order"
    # Severity bands appear in vocabulary order.
    severities = [ACTION_VOCABULARY.index(r.recommended_action) for r in ws]
    assert severities == sorted(severities)


def test_worksheet_rows_grounded_with_both_hold_rows_cited(live_result):
    for r in live_result.worksheet:
        assert r.provenance, f"row {r.uid} carries no provenance"
        sources = {p.source for p in r.provenance}
        assert "sanctions_hold_warehouse" in sources, r.uid
        assert "sanctions_hold_admin" in sources, r.uid
        assert r.warehouse_status in {"blocked", "no_hold"}
        assert r.admin_status in {"blocked", "no_hold"}


def test_worksheet_gap_rows_match_gap_key(live_result, ground_truth):
    by_uid = {r.uid: r for r in live_result.worksheet}
    for gap in ground_truth["block_status_gaps"]:
        row = by_uid[gap["uid"]]
        assert row.gap_type == gap["gap_type"]
        assert row.warehouse_status == gap["warehouse_status"]
        assert row.admin_status == gap["admin_status"]
    # No fabricated gaps: every gap-typed row is in the answer key.
    assert {r.uid for r in live_result.worksheet if r.gap_type is not None} == {
        g["uid"] for g in ground_truth["block_status_gaps"]
    }


def test_privileged_tag_flagged_never_obeyed(live_result, ring):
    """The internal do-not-block tag is a finding, not an instruction: the
    account still appears (review-only), the flag is set, the action is the
    named severe flag, and the tag's account row is cited field-level."""
    row = next(r for r in live_result.worksheet if r.uid == ring["PRIVILEGED"])
    assert row.internal_tag_flag is True
    assert row.recommended_action == "flags_internal_tag_for_review"
    assert row.hops is None and row.exposure_usdt == 0.0  # review-only, not exposure
    assert any(p.field == "internal_tag" for p in row.provenance)
    assert "flagged for review" in row.statement
    # never obeyed: being tagged exempts nothing — the row exists and demands review
    assert row.uid in {r.uid for r in live_result.worksheet}


def test_fabricated_pointer_fails_closed(conn, live_result):
    row = live_result.worksheet[0].model_copy(update={
        "provenance": [Provenance(source="transactions", row_key="SIMTX999999")],
    })
    with pytest.raises(UnresolvableCitationError):
        assert_worksheet_resolvable(conn, [row])
    empty = live_result.worksheet[0].model_copy(update={"provenance": []})
    with pytest.raises(UnresolvableCitationError):
        assert_worksheet_resolvable(conn, [empty])


def test_worksheet_and_escalations_zero_banned_terms(live_result):
    for r in live_result.worksheet:
        low = r.statement.lower()
        assert not [t for t in BANNED_TERMS if t in low], r.statement
    for e in live_result.escalations:
        low = f"{e.subject} {e.body}".lower()
        assert not [t for t in BANNED_TERMS if t in low], e.escalation_id


# --------------------------------------------------------------------------- #
# escalations — drafted, never sent; suppression surfaced
# --------------------------------------------------------------------------- #
def test_escalations_expected_set_full_equality(live_result, ring):
    expected = {
        (ring["TRUST"], "reconciliation_gap"),
        (ring["SHELL_TR"], "reconciliation_gap"),
        (ring["KINGPIN"], "exposed_unblocked"),
        (ring["SHELL_NZ"], "exposed_unblocked"),
        (ring["SHELL_AE"], "exposed_unblocked"),
        (ring["SHELL_HK"], "exposed_unblocked"),
        (ring["SHELL_CN"], "exposed_unblocked"),
    }
    assert {(e.uid, e.kind) for e in live_result.escalations} == expected
    assert live_result.suppressed_escalations == []


def test_escalations_are_drafts_never_sent(live_result):
    ids = []
    for e in live_result.escalations:
        assert e.status == DRAFT_STATUS
        assert "not sent" in e.body.lower()
        assert e.citations and e.provenance
        assert e.escalation_id.startswith(f"ESC-{live_result.designation.designation_id}-")
        ids.append(e.escalation_id)
    assert len(ids) == len(set(ids)), "escalation ids must be unique"
    # No draft object can even represent a sent state from this codebase.
    assert {e.status for e in live_result.escalations} == {DRAFT_STATUS}


def test_escalation_suppression_is_surfaced_never_silent(
    conn, sweep_designations, tmp_path, monkeypatch
):
    """Force a calibration violation into one template: the affected drafts
    are suppressed WITH the reason and the rest still emit — nothing silently
    disappears, nothing invalid ships."""
    import okojo.sweep.escalations as esc

    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)

    doctored = lambda row, d: "This hold is definitely required."  # noqa: E731
    monkeypatch.setattr(esc, "_gap_body", doctored)
    drafts, suppressed = draft_escalations(conn, live, res.worksheet)

    gap_uids = {r.uid for r in res.worksheet if r.gap_type is not None}
    assert {s.uid for s in suppressed} == gap_uids
    for s in suppressed:
        assert "calibration violation" in s.reason and "definitely" in s.reason
    assert {e.kind for e in drafts} == {"exposed_unblocked"}


def test_decoy_worksheet_and_escalations_empty(conn, sweep_designations, tmp_path):
    _, decoy = sweep_designations
    res = run_sweep(decoy, out_dir=tmp_path / "decoy", conn=conn)
    assert res.worksheet == []
    assert res.escalations == []
    assert res.suppressed_escalations == []
    assert res.audit_verified


# --------------------------------------------------------------------------- #
# Part I-B S2 — foreign national-list plants: signal exposure + name-match rows
# --------------------------------------------------------------------------- #
@pytest.fixture()
def lead_result(conn, foreign_designations, tmp_path):
    lead, _ = foreign_designations
    return run_sweep(lead, out_dir=tmp_path / "lead", conn=conn)


@pytest.fixture()
def name_only_result(conn, foreign_designations, tmp_path):
    _, name_only = foreign_designations
    return run_sweep(name_only, out_dir=tmp_path / "name_only", conn=conn)


def test_signal_exposed_rows_use_signal_action_and_language(lead_result):
    """Under a SIGNAL-type foreign designation, EVERY flow-exposed row takes the
    review-tier foreign-signal action and signal language — never an obligation
    action (propose/confirm a hold) and never a legal-effect assertion."""
    exposed = [r for r in lead_result.worksheet if r.hops is not None]
    assert exposed, "the lead-time plant must expose accounts"
    for r in exposed:
        assert r.recommended_action == "flags_foreign_signal_exposure_for_review"
        assert "risk signal" in r.statement.lower()
        assert "not a designation obligation" in r.statement.lower()
    # No obligation action appears anywhere in a signal worksheet.
    actions = {r.recommended_action for r in lead_result.worksheet}
    assert "proposes_designation_hold_review" not in actions
    assert "proposes_confirm_existing_hold" not in actions


def test_name_only_plant_yields_one_identity_review_row(name_only_result, ring):
    """The name-only plant (no wallet, no domestic designation) yields exactly
    one review-tier identity row for the matched account, grounded on its
    account row — never a flow-exposure or adjacency row."""
    ws = name_only_result.worksheet
    assert len(ws) == 1
    row = ws[0]
    assert row.uid == ring["SIBLING"]
    assert row.recommended_action == "flags_name_match_for_identity_review"
    assert row.hops is None and row.exposure_usdt == 0.0
    assert "identity review" in row.statement.lower()
    assert row.provenance  # grounded on the account row
    assert name_only_result.exposure.exposed == []


def test_domestic_name_match_adds_no_identity_row(live_result):
    """The domestic live name matches an already-EXPOSED shell, so it adds no
    separate identity row — the additive rule only fires for accounts surfaced
    by neither flow nor linkage (proof the domestic worksheet is unchanged)."""
    actions = {r.recommended_action for r in live_result.worksheet}
    assert "flags_name_match_for_identity_review" not in actions


def test_signal_output_carries_zero_legal_effect_terms(lead_result):
    """Calibrated-language ban: no signal-type statement or escalation body may
    assert a legal effect of a foreign listing."""
    from okojo.sweep import calibrated_language_violations

    for r in lead_result.worksheet:
        assert calibrated_language_violations(r.statement) == [], r.statement
    for e in lead_result.escalations:
        assert calibrated_language_violations(f"{e.subject} {e.body}") == [], e.escalation_id
    # The signal escalations are review-flavoured, not hold proposals.
    assert {e.kind for e in lead_result.escalations} <= {
        "foreign_signal_exposure", "reconciliation_gap",
    }


def test_signal_escalation_calibration_violation_suppressed_never_silent(
    conn, foreign_designations, tmp_path, monkeypatch
):
    """Force a legal-effect assertion into the signal escalation template: the
    affected drafts are suppressed WITH the reason, the rest still emit."""
    import okojo.sweep.escalations as esc

    lead, _ = foreign_designations
    res = run_sweep(lead, out_dir=tmp_path / "s", conn=conn)

    doctored = lambda row, d: "This account must be blocked immediately."  # noqa: E731
    monkeypatch.setattr(esc, "_signal_exposure_body", doctored)
    drafts, suppressed = draft_escalations(conn, lead, res.worksheet)

    signal_uids = {
        r.uid for r in res.worksheet
        if r.hops is not None and r.gap_type is None
        and r.warehouse_status == "no_hold" and r.admin_status == "no_hold"
    }
    assert signal_uids and {s.uid for s in suppressed} == signal_uids
    for s in suppressed:
        assert "calibration violation" in s.reason and "must be blocked" in s.reason
    # The reconciliation-gap drafts (neutral, untouched) still emit.
    assert {e.kind for e in drafts} == {"reconciliation_gap"}


def test_worksheet_build_guard_rejects_signal_legal_effect(lead_result):
    """The worksheet build-time tripwire fails closed on a signal row that
    asserts a legal effect — defence in depth behind the authored-clean text."""
    from okojo.sweep import CalibratedLanguageError, assert_calibrated_signal_language

    bad = lead_result.worksheet[0].model_copy(update={
        "statement": "This account is sanctioned and must be blocked.",
    })
    with pytest.raises(CalibratedLanguageError):
        assert_calibrated_signal_language([bad])
