"""The bounded drafter-critic revision loop: raises coverage, stays grounded,
terminates deterministically, and flags (never fabricates) what it cannot fill.
"""

from __future__ import annotations

import pytest

from okojo.aggregator import build_profile
from okojo.entity import build_backbone
from okojo.network import expand
from okojo.remarks import mine_remarks
from okojo.sar import (
    MAX_REVISION_ITERATIONS,
    calibration_violations,
    draft_with_critic,
    validate_grounding,
)


def _case(conn, uid):
    """Assemble the drafter's inputs for one subject (advisory left to None so the
    predicate fill exercises the on-chain-exposure path)."""
    profile = build_profile(conn, uid)
    expansion = expand(conn, uid, max_hops=2)
    tells = mine_remarks(conn, backbone=build_backbone(conn))
    return profile, expansion, tells


def _uid_for_role(conn, role: str) -> int:
    return next(a["uid"] for a in conn.all_accounts() if a["role_in_ring"] == role)


@pytest.fixture()
def controller_uid(conn) -> int:
    return _uid_for_role(conn, "ultimate_controller")


@pytest.fixture()
def redherring_uid(conn) -> int:
    # The "privileged internal" red herring: sparse direct evidence, so required
    # rubric elements stay unfillable -> a deterministic human-fallback case.
    return _uid_for_role(conn, "privileged_internal_redherring")


def test_loop_converges_and_raises_coverage(conn, controller_uid):
    sar, h = draft_with_critic(conn, *_case(conn, controller_uid), None)
    assert h.initial.coverage < h.final.coverage       # revision genuinely helped
    assert h.final.coverage == 1.0
    assert h.converged and not h.flagged
    assert h.iterations >= 1
    # revised draft is still fully grounded, resolvable, and calibrated
    assert validate_grounding(conn, sar).fully_resolved
    assert calibration_violations(sar) == []


def test_loop_is_deterministically_bounded(conn):
    """No subject ever exceeds the hard iteration cap."""
    for a in conn.all_accounts():
        _, h = draft_with_critic(conn, *_case(conn, a["uid"]), None)
        assert h.iterations <= MAX_REVISION_ITERATIONS


def test_human_fallback_flags_unfillable_elements(conn, redherring_uid):
    sar, h = draft_with_critic(conn, *_case(conn, redherring_uid), None)
    assert not h.converged
    assert h.flagged                                   # something was left for a human
    assert h.final.coverage < 1.0
    # the filing note surfaces the flagged elements for analyst review
    assert "CRITIC NOTE" in sar.filing_note
    for key in h.flagged:
        assert key in sar.filing_note
    # crucially: flagging is NOT fabrication — every claim still resolves
    assert validate_grounding(conn, sar).fully_resolved
    assert calibration_violations(sar) == []


def test_loop_never_fabricates_across_all_subjects(conn):
    """Whether it converges or falls back, no draft ever cites unresolvable evidence."""
    for a in conn.all_accounts():
        sar, _ = draft_with_critic(conn, *_case(conn, a["uid"]), None)
        report = validate_grounding(conn, sar)
        assert report.fully_grounded and report.fully_resolved


def test_loop_is_deterministic(conn, controller_uid):
    a_sar, a_h = draft_with_critic(conn, *_case(conn, controller_uid), None)
    b_sar, b_h = draft_with_critic(conn, *_case(conn, controller_uid), None)
    assert [c.element for c in a_sar.claims] == [c.element for c in b_sar.claims]
    assert a_h.revisions == b_h.revisions
    assert a_h.final.summary() == b_h.final.summary()
