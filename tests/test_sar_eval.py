"""Phase 4 eval — SAR grounding coverage + the drafter-critic ablation.

Two scorecards ship with the capability (discipline rule: every capability ships
its eval), both printed under ``capsys.disabled()`` like the phase-2 / advisory
scorecards:

1. **Grounding coverage** — on end-to-end pipeline runs, every SAR claim is
   grounded AND every citation resolves to an actual evidence row; and the
   fail-closed contract rejects an injected unresolvable claim.
2. **Critic ablation (with vs. without the loop)** — the covered rubric-element
   set is scored against a committed gold key (``tests/data/sar_rubric_gold.json``,
   a SEPARATE key so the seeded generator is untouched). With the Critic loop the
   coverage equals the gold (P=R=F1=1.0); without it, recall is strictly lower.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from okojo.eval import score
from okojo.orchestrator import run_case
from okojo.provenance import Provenance
from okojo.sar import (
    SarClaim,
    SarDraft,
    UnresolvableCitationError,
    assert_resolvable,
    validate_grounding,
)

_GOLD = json.loads((Path(__file__).parent / "data" / "sar_rubric_gold.json").read_text(encoding="utf-8"))
_SUBJECTS = _GOLD["subjects"]


def _uid_for_role(conn, role: str) -> int:
    return next(a["uid"] for a in conn.all_accounts() if a["role_in_ring"] == role)


def _covered(critique) -> set[str]:
    return {g.key for g in critique.grades if g.passed}


# --------------------------------------------------------------------------- #
# 1) Grounding-coverage scorecard
# --------------------------------------------------------------------------- #
def test_sar_grounding_coverage_scorecard(conn, tmp_path, capsys):
    rows = []
    all_ok = True
    for spec in _SUBJECTS:
        uid = _uid_for_role(conn, spec["role"])
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}", render_graph=False)
        rep = validate_grounding(conn, res.sar)
        ok = rep.fully_grounded and rep.fully_resolved
        all_ok = all_ok and ok
        rows.append((spec["role"], rep.total_claims, rep.grounded_claims, rep.resolved_claims, ok))

    with capsys.disabled():
        print("\nSAR grounding-coverage scorecard (end-to-end pipeline runs):")
        for role, total, g, r, ok in rows:
            print(f"  {role:32s} claims={total:2d} grounded={g:2d} resolved={r:2d} ok={ok}")
        print(f"  all_fully_grounded_and_resolved: {all_ok}")

    assert all_ok


def test_uncitable_claim_is_rejected_fail_closed(conn):
    """The grounding contract fails closed on a pointer to a non-existent row."""
    draft = SarDraft(
        subject_uid=1, subject_name="X", filing_note="", disclaimer="",
        claims=[SarClaim(element="who", statement="Cites a ghost row.",
                         provenance=[Provenance(source="accounts", row_key="uid:-1")])],
    )
    with pytest.raises(UnresolvableCitationError):
        assert_resolvable(conn, draft)


# --------------------------------------------------------------------------- #
# 2) Critic ablation scorecard (with vs. without the revision loop)
# --------------------------------------------------------------------------- #
def test_critic_ablation_scorecard(conn, tmp_path, capsys):
    gold_pairs: set[tuple[str, str]] = set()
    with_pairs: set[tuple[str, str]] = set()
    without_pairs: set[tuple[str, str]] = set()
    per_subject = []

    for spec in _SUBJECTS:
        role = spec["role"]
        uid = _uid_for_role(conn, role)
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}", render_graph=False)
        h = res.critique_history
        gold = set(spec["expect_covered"])
        base = _covered(h.initial)      # template-first draft (no revision)
        final = _covered(h.final)       # after the bounded Critic loop

        gold_pairs |= {(role, e) for e in gold}
        with_pairs |= {(role, e) for e in final}
        without_pairs |= {(role, e) for e in base}
        per_subject.append((role, len(base), len(final), len(gold), sorted(gold - base)))

    with_score = score(with_pairs, gold_pairs)
    without_score = score(without_pairs, gold_pairs)

    with capsys.disabled():
        print("\nSAR Critic ablation scorecard (covered rubric elements vs. gold key):")
        for role, nb, nf, ng, filled in per_subject:
            print(f"  {role:32s} base={nb} -> critic={nf} / gold={ng}  loop_filled={filled}")
        print(f"  WITH Critic loop:    {with_score}")
        print(f"  WITHOUT Critic loop: {without_score}")

    # With the loop, coverage matches the gold exactly.
    assert with_score.precision == 1.0 and with_score.recall == 1.0 and with_score.f1 == 1.0
    # The base draft never over-claims (everything it covers is in gold)...
    assert without_score.precision == 1.0
    # ...but it misses coverable elements the loop recovers — the measured value.
    assert without_score.recall < 1.0
    assert with_score.recall > without_score.recall


def test_gold_key_matches_system_coverage(conn, tmp_path):
    """Guard: the committed gold equals the Critic's achieved coverage per subject
    (so the ablation's P=R=1.0 is a real result, not a mis-authored key)."""
    for spec in _SUBJECTS:
        uid = _uid_for_role(conn, spec["role"])
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}", render_graph=False)
        assert _covered(res.critique_history.final) == set(spec["expect_covered"]), spec["role"]
