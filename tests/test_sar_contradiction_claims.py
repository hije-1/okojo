"""Phase 5 Slice D: contradictions reach the SAR draft, citing both sides.

The two-stage grounding contract is the point: a contradiction claim asserts a
conflict between what the subject said and what the evidence shows, so it must
cite the RFI row AND the rebutting evidence row, and both must resolve.

The FinCEN rubric is deliberately NOT changed here. ``contradiction`` maps to no
rubric element, so CRITIC_VERSION, the committed rubric gold key and the
ablation numbers are untouched. Letting contradictions corroborate what/why is a
real improvement, but it belongs in its own slice with its own version bump and
a before/after ablation - see docs/Build-Plan.md.
"""

from __future__ import annotations

from okojo.orchestrator import run_case
from okojo.sar import FINCEN_RUBRIC, critique, validate_grounding


def _contradiction_claims(draft):
    return [c for c in draft.claims if c.element == "contradiction"]


def test_draft_carries_one_claim_per_adjudicated_contradiction(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    claims = _contradiction_claims(res.sar)
    assert len(claims) == len(res.contradictions.contradictions) == 2
    for adj in res.contradictions.contradictions:
        assert any(adj.claim_id in c.statement for c in claims), adj.claim_id


def test_each_contradiction_cites_both_sides(conn, trust_uid, tmp_path):
    """The RFI row AND at least one non-RFI evidence row."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    for c in _contradiction_claims(res.sar):
        sources = {p.source for p in c.provenance}
        assert "rfi" in sources, "must cite the assertion"
        assert sources - {"rfi"}, "must cite the rebutting evidence"


def test_contradiction_claims_are_grounded_and_resolvable(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    report = validate_grounding(conn, res.sar)
    assert report.fully_grounded and report.fully_resolved
    assert not report.unresolved


def test_contradiction_language_stays_calibrated(conn, trust_uid, tmp_path):
    """The draft surfaces an inconsistency; it never concludes the subject lied."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    for c in _contradiction_claims(res.sar):
        low = c.statement.lower()
        assert "inconsistent with" in low
        assert "surfaced for analyst review" in low
        for banned in ("lied", "false statement", "proves", "fraudulent"):
            assert banned not in low, banned


def test_rubric_is_untouched_by_the_new_claim_type():
    """No rubric element is satisfied by a contradiction claim (Phase-5 scope)."""
    mapped = {e for el in FINCEN_RUBRIC for e in el.claim_elements}
    assert "contradiction" not in mapped


def test_ablation_coverage_unchanged_by_contradictions(conn, trust_uid, tmp_path):
    """Adding contradiction claims must not move the Critic's covered set."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    covered = {g.key for g in res.critique_history.final.grades if g.passed}

    stripped = res.sar.model_copy(update={
        "claims": [c for c in res.sar.claims if c.element != "contradiction"],
    })
    assert {g.key for g in critique(stripped).grades if g.passed} == covered


def test_subject_without_rfi_gets_no_contradiction_claims(conn, ground_truth, tmp_path):
    uid = ground_truth["privileged_redherring_uid"]
    res = run_case(uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.contradictions is None
    assert _contradiction_claims(res.sar) == []
