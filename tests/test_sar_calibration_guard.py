"""The SAR calibration guard, wired LIVE at draft-validation time (Phase 8 sign-off).

``calibration_violations`` has existed since Phase 1 but had **no live call site** —
a control with the shape but not the substance of enforcement (exactly the pathology
the P8-G falsification discipline exists to kill). Phase 8 sign-off wires
``assert_calibrated`` fail-closed into ``build_sar`` and the drafter-critic loop,
alongside the two-step grounding contract (``assert_grounded`` / ``assert_resolvable``).

These tests lock the LIVE call site: each banned term is caught through
``assert_calibrated`` (the function the pipeline now calls), and a banned term that
reaches a REAL ``build_sar`` draft is rejected — not silently passed. The clean
gold drafts are unaffected (proven separately: every roster + isolated subject's
draft has zero calibration violations, so wiring the guard moves no scorecard).
"""

from __future__ import annotations

import pytest

from okojo.aggregator import build_profile
from okojo.entity import build_backbone
from okojo.network import expand
from okojo.provenance import Provenance
from okojo.remarks import mine_remarks
from okojo.sar import (
    BANNED_TERMS,
    CalibrationViolationError,
    SarClaim,
    SarDraft,
    assert_calibrated,
    build_sar,
    calibration_violations,
)


def _grounded(statement: str) -> SarClaim:
    """A minimal grounded claim (a real pointer, so only calibration is at issue)."""
    return SarClaim(element="what", statement=statement,
                    provenance=[Provenance(source="accounts", row_key="uid:1")])


@pytest.mark.parametrize("term", list(BANNED_TERMS))
def test_each_banned_term_rejected_by_live_guard(term):
    """The guard's term list catches EVERY banned term through the LIVE call site
    (``assert_calibrated`` — the function ``build_sar`` and the loop now call)."""
    draft = SarDraft(subject_uid=1, subject_name="X", filing_note="", disclaimer="",
                     claims=[_grounded(f"The subject {term} moved the funds.")])
    assert calibration_violations(draft)          # the detector sees it
    with pytest.raises(CalibrationViolationError):
        assert_calibrated(draft)                  # the LIVE guard rejects it fail-closed


def test_clean_draft_passes_calibration():
    """A calibrated draft is a no-op through the guard (no false positive)."""
    draft = SarDraft(subject_uid=1, subject_name="X", filing_note="", disclaimer="",
                     claims=[_grounded("The subject is proposed for analyst review.")])
    assert calibration_violations(draft) == []
    assert_calibrated(draft)                       # does not raise


def _case(conn, uid):
    """The drafter's real inputs for one subject (advisory left None)."""
    profile = build_profile(conn, uid)
    expansion = expand(conn, uid, max_hops=2)
    tells = mine_remarks(conn, backbone=build_backbone(conn))
    return profile, expansion, tells


def test_live_build_sar_rejects_injected_banned_term(conn):
    """The WIRING is live end-to-end: a banned term reaching a REAL ``build_sar``
    draft is rejected fail-closed. Injection is at the fixture: the subject name
    flows verbatim into the WHO claim, so a doctored name plants a banned term in a
    genuinely-built draft. Without the ``assert_calibrated`` call inside
    ``build_sar`` this draft would pass silently — the dead-guard pathology this
    slice removes."""
    uid = next(a["uid"] for a in conn.all_accounts()
               if a["role_in_ring"] == "ultimate_controller")
    profile, expansion, tells = _case(conn, uid)

    # A clean subject -> the real drafter produces a clean, calibrated draft.
    clean = build_sar(conn, profile, expansion, tells, None)
    assert calibration_violations(clean) == []

    # Inject a banned term into the fixture; the SAME real build_sar path now
    # rejects the draft at its validation step.
    doctored = profile.model_copy(update={"subject_name": f"{profile.subject_name} definitely"})
    with pytest.raises(CalibrationViolationError):
        build_sar(conn, doctored, expansion, tells, None)
