"""Phase 6: the persistent case graph — idempotent, reproducible, and the
recidivism plant surfaced at case open.

The recidivism scorecard runs the five gold roles and scores the surfaced
flags against ground_truth["recidivist_uids"] — the "cleared five prior
reviews" account must flag, and nothing else may (the trust's planted
prior_review_count of 1 is the near-miss negative). This is also where the
decision-trace gold's recidivism_surfaced field is asserted (deferred from
Slice C by design — see that key's readme).
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.casegraph import CaseGraphStore
from okojo.eval import score
from okojo.orchestrator import run_case

_GOLD = json.loads(
    (Path(__file__).parent / "data" / "decision_trace_gold.json").read_text(encoding="utf-8")
)


def _uid_for_role(conn, role: str) -> int:
    return next(a["uid"] for a in conn.all_accounts() if a["role_in_ring"] == role)


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-01-01T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}+00:00"

    return clock


# --- store mechanics ---------------------------------------------------------

def test_rerun_is_idempotent(conn, trust_uid, tmp_path):
    """Re-running the same case upserts — history is replaced, never duplicated."""
    store_path = tmp_path / "case_graph.sqlite"
    run_case(trust_uid, conn=conn, out_dir=tmp_path / "a", render_graph=False,
             case_store_path=store_path, audit_clock=_counter())
    first = CaseGraphStore(store_path).dump()
    run_case(trust_uid, conn=conn, out_dir=tmp_path / "b", render_graph=False,
             case_store_path=store_path, audit_clock=_counter())
    second = CaseGraphStore(store_path).dump()
    assert first == second
    assert len(first["cases"]) == 1


def test_same_sequence_two_stores_identical(conn, trust_uid, ground_truth, tmp_path):
    """Recording the same case sequence into two fresh stores yields identical
    dumps — the persistence layer adds no nondeterminism (no timestamps, all
    writes sorted, all reads ordered)."""
    uids = [ground_truth["ultimate_controller_uid"], trust_uid,
            ground_truth["recidivist_uids"][0]]
    dumps = []
    for side in ("x", "y"):
        store_path = tmp_path / side / "case_graph.sqlite"
        for uid in uids:
            run_case(uid, conn=conn, out_dir=tmp_path / side / f"c{uid}",
                     render_graph=False, case_store_path=store_path,
                     audit_clock=_counter())
        dumps.append(CaseGraphStore(store_path).dump())
    assert dumps[0] == dumps[1]
    assert len(dumps[0]["cases"]) == len(uids)


def test_store_isolation_under_out_dir(conn, trust_uid, tmp_path):
    """A run with an out_dir gets a store isolated under it: no history leaks
    in from other runs, and none leaks out to the shared default."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "solo", render_graph=False)
    assert res.recidivism is not None
    assert res.recidivism.prior_case_ids == []
    assert res.recidivism.entity_overlaps == []
    assert (tmp_path / "solo" / "case_graph.sqlite").exists()


# --- cross-case memory -------------------------------------------------------

def test_cross_case_entity_overlap_shared_device(conn, ground_truth, tmp_path):
    """The failure mode the case graph exists for: investigating the employee
    cutout first leaves its shared device on record, so opening the
    recidivist's case surfaces the overlap (they share a planted device
    fingerprint), plus the counterparty naming from the earlier expansion."""
    store_path = tmp_path / "case_graph.sqlite"
    employee_uid = _uid_for_role(conn, "employee_cutout")
    recidivist_uid = ground_truth["recidivist_uids"][0]

    run_case(employee_uid, conn=conn, out_dir=tmp_path / "emp", render_graph=False,
             case_store_path=store_path)
    res = run_case(recidivist_uid, conn=conn, out_dir=tmp_path / "rec",
                   render_graph=False, case_store_path=store_path)

    view = res.recidivism
    assert view is not None
    overlap_kinds = {o.kind for o in view.entity_overlaps}
    assert "device" in overlap_kinds, "the planted shared device must surface"
    device_overlaps = [o for o in view.entity_overlaps if o.kind == "device"]
    assert any(f"case_{employee_uid}" in o.case_ids for o in device_overlaps)
    # the employee's expansion also named the recidivist as a counterparty
    named = [o for o in view.entity_overlaps
             if o.kind == "counterparty_account" and o.key == str(recidivist_uid)]
    assert named and f"case_{employee_uid}" in named[0].case_ids

    # and the roster now knows the employee has a case on record via the store
    from okojo.network import build_roster
    roster = build_roster(conn, res.expansion, tmp_path / "nowhere",
                          store=CaseGraphStore(store_path))
    emp_row = next(r for r in roster if r.uid == employee_uid)
    assert emp_row.has_case_file


# --- recidivism surfacing ----------------------------------------------------

def test_recidivism_scorecard(conn, tmp_path, capsys, ground_truth):
    """Predicted recidivism flags across the five gold roles vs the planted
    answer key — and the decision-trace gold's recidivism_surfaced field."""
    predicted: set[int] = set()
    lines = []
    for spec in _GOLD["subjects"]:
        uid = _uid_for_role(conn, spec["role"])
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}", render_graph=False)
        view = res.recidivism
        assert view is not None
        if view.is_recidivist:
            predicted.add(uid)
        assert view.is_recidivist == spec["expected"]["recidivism_surfaced"], spec["role"]
        lines.append(
            f"  {spec['role']:32s} prior_reviews={view.prior_review_count} "
            f"status={view.account_status:14s} flagged={view.is_recidivist}"
        )

        # the flag is stamped into the chain, with calibrated language
        actions = {(r["actor"], r["action"]) for r in res.audit_records}
        expected_action = ("case_graph", "recidivism_flagged" if view.is_recidivist
                           else "history_clear")
        assert expected_action in actions, spec["role"]

    gold = set(ground_truth["recidivist_uids"])
    result = score(predicted, gold)
    with capsys.disabled():
        print("\nRecidivism-surfacing scorecard (planted 'cleared five prior "
              "reviews' account):")
        for ln in lines:
            print(ln)
        print(f"  recidivism_flagging: {result}")
    assert result.precision == 1.0 and result.recall == 1.0 and result.f1 == 1.0


def test_recidivist_flag_fires_on_cold_store(conn, ground_truth, tmp_path):
    """The planted review history predates Okojo, so the flag must fire on a
    store with no prior cases at all."""
    uid = ground_truth["recidivist_uids"][0]
    res = run_case(uid, conn=conn, out_dir=tmp_path / "cold", render_graph=False)
    view = res.recidivism
    assert view is not None and view.is_recidivist
    assert view.prior_review_count == 5
    assert view.account_status == "retain_monitor"
    assert view.prior_case_ids == []  # cold store — the account fields carried it
