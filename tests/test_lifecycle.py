"""Phase 8 Part IV V1a: the counterparty-lifecycle decision + the lifecycle
module, on constructed fixtures.

The eighth bounded decision rule (propose_unblock / propose_offboard /
hold_pending) is a pure function of three evidence booleans; these tests
exercise every branch — including the two the planted scenario never takes
(Q9: acknowledged-but-still-dealing; the pre-designation-only customer who earns
no notification) and the Q5 precedence fixture (recidivism dominates an
acknowledged-and-stopped relationship). The full per-persona P8-A exact-set eval
against the answer key lives in src/okojo/eval/test_lifecycle_eval.py.
"""

from __future__ import annotations

from okojo.agency import DECISION_OUTCOMES, decide_counterparty_lifecycle
from okojo.sweep.lifecycle import (
    LIFECYCLE_OFFBOARD_TERMINAL,
    LIFECYCLE_STATES,
    derive_counterparty_lifecycle_state,
    has_post_designation_dealing,
    is_stop_verified,
    render_counterparty_notification,
)
from okojo.agency import TippingOffRisk, assert_no_tipping_off

import pytest


# --- the eighth decision: outcome set + every branch -------------------------

def test_counterparty_lifecycle_outcome_set_registered():
    assert DECISION_OUTCOMES["counterparty_lifecycle"] == (
        "propose_unblock", "propose_offboard", "hold_pending",
    )


def test_unblock_only_when_acknowledged_and_stopped():
    rec = decide_counterparty_lifecycle(
        1, acknowledged=True, stop_verified=True, repeat_offender=False)
    assert rec.outcome == "propose_unblock"
    assert rec.decision_id == "counterparty_lifecycle"
    assert rec.evidence == {"uid": 1, "acknowledged": True,
                            "stop_verified": True, "repeat_offender": False}


def test_hold_pending_when_no_acknowledgment():
    rec = decide_counterparty_lifecycle(
        2, acknowledged=False, stop_verified=False, repeat_offender=False)
    assert rec.outcome == "hold_pending"


def test_hold_pending_when_acknowledged_but_not_stopped():
    """Q9 dormant branch: an acknowledgment WITHOUT a verified stop (the customer
    kept dealing after acknowledging) never proposes unblock."""
    rec = decide_counterparty_lifecycle(
        3, acknowledged=True, stop_verified=False, repeat_offender=False)
    assert rec.outcome == "hold_pending"


def test_offboard_when_repeat_offender():
    rec = decide_counterparty_lifecycle(
        4, acknowledged=False, stop_verified=False, repeat_offender=True)
    assert rec.outcome == "propose_offboard"


def test_recidivism_dominates_acknowledged_and_stopped():
    """Q5 precedence fixture: a repeat offender who ALSO acknowledged this
    counterparty and stopped dealing STILL gets propose_offboard — an
    acknowledgment does not reset a prior acknowledged relationship."""
    rec = decide_counterparty_lifecycle(
        5, acknowledged=True, stop_verified=True, repeat_offender=True)
    assert rec.outcome == "propose_offboard"


def test_lifecycle_decision_is_pure():
    a = decide_counterparty_lifecycle(9, acknowledged=True, stop_verified=True,
                                      repeat_offender=False)
    b = decide_counterparty_lifecycle(9, acknowledged=True, stop_verified=True,
                                      repeat_offender=False)
    assert a.summary() == b.summary()


# --- the lifecycle state machine ---------------------------------------------

def test_state_terminals_win():
    assert derive_counterparty_lifecycle_state(notification_drafted=True, acknowledged=True,
                                  stop_verified=True, outcome="propose_offboard") \
        == LIFECYCLE_OFFBOARD_TERMINAL
    assert derive_counterparty_lifecycle_state(notification_drafted=True, acknowledged=True,
                                  stop_verified=True, outcome="propose_unblock") \
        == "unblock_proposed"


def test_state_reports_furthest_evidence_milestone_under_hold():
    # hold_pending, no acknowledgment, notification drafted -> notification_drafted
    assert derive_counterparty_lifecycle_state(notification_drafted=True, acknowledged=False,
                                  stop_verified=False, outcome="hold_pending") \
        == "notification_drafted"
    # hold_pending, acknowledged, not stopped -> acknowledgment_recorded
    assert derive_counterparty_lifecycle_state(notification_drafted=True, acknowledged=True,
                                  stop_verified=False, outcome="hold_pending") \
        == "acknowledgment_recorded"
    # bare detected exposure (notification suppressed) -> exposure_detected
    assert derive_counterparty_lifecycle_state(notification_drafted=False, acknowledged=False,
                                  stop_verified=False, outcome="hold_pending") \
        == "exposure_detected"


def test_lifecycle_states_are_ordered_and_complete():
    assert LIFECYCLE_STATES == (
        "exposure_detected", "notification_drafted", "acknowledgment_recorded",
        "stop_dealing_verified", "unblock_proposed",
    )


# --- grounded timing helpers (pure over dealing rows) ------------------------

def _tx(tx_id: str, date: str) -> dict:
    return {"tx_id": tx_id, "timestamp": f"{date}T09:00:00"}


def test_post_designation_dealing_detected_only_after_the_date():
    dealings = [_tx("T1", "2025-03-15"), _tx("T2", "2025-07-10")]
    assert has_post_designation_dealing(dealings, "2025-06-01") is True
    # all pre-designation
    assert has_post_designation_dealing([_tx("T1", "2025-03-15")], "2025-06-01") is False


def test_stop_verified_is_no_dealing_after_the_acknowledgment_date():
    # Marta's arc: last dealing 2025-07-10, acknowledged 2025-08-01 -> stopped.
    dealings = [_tx("T1", "2025-03-15"), _tx("T2", "2025-07-10")]
    assert is_stop_verified(dealings, "2025-08-01") is True
    # kept dealing after acknowledging (2025-09-05 > 2025-08-01) -> not stopped.
    dealings2 = dealings + [_tx("T3", "2025-09-05")]
    assert is_stop_verified(dealings2, "2025-08-01") is False


# --- the subject-facing notification is guard-safe by construction ------------

def test_notification_renders_and_clears_the_guard():
    text = render_counterparty_notification("Marta Kovanen", "Kavelith Digital Exchange")
    assert "Kavelith Digital Exchange" in text
    assert "Marta Kovanen" in text
    assert "Terms and Conditions" in text
    # It clears the fail-closed anti-tipping-off validator (Q4: authored
    # guard-safe, still validated) — no exception.
    assert_no_tipping_off(text)


def test_notification_guard_catches_a_smuggled_counterparty_name():
    """Defense in depth: a counterparty name carrying a banned token would trip
    the fail-closed guard on the rendered text (the wiring then suppresses)."""
    text = render_counterparty_notification("A Customer", "Sanctions Clearing Ltd")
    with pytest.raises(TippingOffRisk):
        assert_no_tipping_off(text)
