"""The SAR grounding contract: no claim without provenance; calibrated language."""

from __future__ import annotations

import pytest

from okojo.orchestrator import run_case
from okojo.provenance import Provenance
from okojo.sar import (
    SarClaim,
    SarDraft,
    UngroundedClaimError,
    assert_grounded,
    calibration_violations,
)


def test_generated_sar_is_fully_grounded(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.sar.claims
    assert res.sar.ungrounded() == []
    assert calibration_violations(res.sar) == []


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
