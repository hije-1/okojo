"""The SAR grounding contract: no claim without provenance; every citation must
resolve to a real evidence row; calibrated language."""

from __future__ import annotations

import pytest

from okojo.orchestrator import run_case
from okojo.provenance import Provenance
from okojo.sar import (
    SarClaim,
    SarDraft,
    UngroundedClaimError,
    UnresolvableCitationError,
    assert_grounded,
    assert_resolvable,
    calibration_violations,
    validate_grounding,
)


def test_generated_sar_is_fully_grounded(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.sar.claims
    assert res.sar.ungrounded() == []
    assert calibration_violations(res.sar) == []


def test_generated_sar_is_fully_resolvable(conn, trust_uid, tmp_path):
    """Every claim's every citation names a row that actually exists."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    report = validate_grounding(conn, res.sar)
    assert report.total_claims == len(res.sar.claims)
    assert report.fully_grounded
    assert report.fully_resolved, f"dangling citations: {report.unresolved}"
    # And the fail-closed assertion is a no-op on a clean draft.
    assert_resolvable(conn, res.sar)


def test_assert_resolvable_rejects_dangling_citation(conn):
    """A well-formed pointer to a NON-existent row is rejected fail-closed."""
    draft = SarDraft(
        subject_uid=1, subject_name="X", filing_note="", disclaimer="",
        claims=[
            SarClaim(element="who", statement="Cites a real subject.",
                     provenance=[conn.all_accounts()[0].provenance]),
            SarClaim(element="what", statement="Cites a ghost account.",
                     provenance=[Provenance(source="accounts", row_key="uid:-999999")]),
        ],
    )
    # Grounding (non-empty) passes; resolvability does not.
    assert_grounded(draft)
    with pytest.raises(UnresolvableCitationError):
        assert_resolvable(conn, draft)
    report = validate_grounding(conn, draft)
    assert report.grounded_claims == 2
    assert report.resolved_claims == 1
    assert len(report.unresolved) == 1


def test_unresolvable_is_an_ungrounded_error_subclass():
    # One `except UngroundedClaimError` catches both fail-closed modes.
    assert issubclass(UnresolvableCitationError, UngroundedClaimError)


def test_assert_grounded_rejects_uncitable_claim():
    draft = SarDraft(
        subject_uid=1, subject_name="X",
        filing_note="", disclaimer="",
        claims=[
            SarClaim(element="who", statement="Grounded.",
                     provenance=[Provenance(source="accounts", row_key="uid:1")]),
            SarClaim(element="what", statement="Uncitable claim.", provenance=[]),
        ],
    )
    assert draft.ungrounded()
    with pytest.raises(UngroundedClaimError):
        assert_grounded(draft)


def test_calibration_flags_overclaiming():
    draft = SarDraft(
        subject_uid=1, subject_name="X", filing_note="", disclaimer="",
        claims=[SarClaim(element="what", statement="The subject autonomously laundered funds.",
                         provenance=[Provenance(source="x", row_key="y")])],
    )
    assert calibration_violations(draft)
