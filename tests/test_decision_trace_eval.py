"""Phase 6 decision-trace eval: the bounded decisions, scored against gold.

The committed key (tests/data/decision_trace_gold.json) is DOMAIN-AUTHORED
from the scenario's planted facts plus the published decision policy — see its
readme — so this eval measures whether the agent's bounded choices land where
the scenario says they should, not whether the code agrees with itself.

Scored as the repo's standard exact-match-via-P/R/F1 over
(role, decision_point, canonical_outcome) triples, plus per-subject effect
assertions (which advisory was surfaced, which claims got follow-up
questions) and a trace<->audit round-trip so the trace being scored IS the
tamper-evident one.

The gold's recidivism_surfaced field is asserted by the casegraph eval once
the persistent case graph lands (Phase 6 Slice D), not here.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.eval import score
from okojo.orchestrator import run_case

_GOLD = json.loads(
    (Path(__file__).parent / "data" / "decision_trace_gold.json").read_text(encoding="utf-8")
)
_SUBJECTS = _GOLD["subjects"]


def _uid_for_role(conn, role: str) -> int:
    return next(a["uid"] for a in conn.all_accounts() if a["role_in_ring"] == role)


def _canonical(decisions: list) -> dict[str, str]:
    """Collapse a decision trace to {decision_point: canonical outcome string}.

    The hop loop records one expand_hop decision per hop, joined in order;
    every other decision point records exactly once.
    """
    out: dict[str, list[str]] = {}
    for d in decisions:
        out.setdefault(d.decision_id, []).append(d.outcome)
    return {k: "->".join(v) for k, v in out.items()}


def _gold_canonical(expected: dict) -> dict[str, str]:
    return {
        "expand_hop": "->".join(expected["expand_hop"]),
        "second_advisory": expected["second_advisory"]["outcome"],
        "re_rfi": expected["re_rfi"]["outcome"],
        "sufficiency": expected["sufficiency"],
        "sar_bar": expected["sar_bar"],
    }


def test_decision_trace_scorecard(conn, tmp_path, capsys):
    predicted: set[tuple] = set()
    gold: set[tuple] = set()
    lines = []
    results = {}

    for spec in _SUBJECTS:
        role = spec["role"]
        uid = _uid_for_role(conn, role)
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}",
                       render_graph=False, max_hops=_GOLD["hop_cap"])
        results[role] = res

        got = _canonical(res.decisions)
        want = _gold_canonical(spec["expected"])
        for point, outcome in got.items():
            predicted.add((role, point, outcome))
        for point, outcome in want.items():
            gold.add((role, point, outcome))

        lines.append(f"  {role:32s}")
        for point in ("expand_hop", "second_advisory", "re_rfi",
                      "sufficiency", "sar_bar"):
            g, w = got.get(point, "-"), want.get(point, "-")
            ok = "OK" if g == w else "MISMATCH"
            lines.append(f"    {point:18s} {g:32s} (expect {w:28s}) {ok}")

    result = score(predicted, gold)
    with capsys.disabled():
        print("\nDecision-trace scorecard (5 bounded decision points, "
              "domain-authored gold key):")
        for ln in lines:
            print(ln)
        print(f"  decision_trace: {result}")

    assert result.precision == 1.0 and result.recall == 1.0 and result.f1 == 1.0

    # --- decision EFFECTS match the gold, not just outcome strings --------- #
    for spec in _SUBJECTS:
        res = results[spec["role"]]
        exp = spec["expected"]

        want_secondary = exp["second_advisory"]["advisory_id"]
        got_secondary = (res.secondary_advisory.advisory_id
                        if res.secondary_advisory else None)
        assert got_secondary == want_secondary, spec["role"]

        want_claims = exp["re_rfi"]["claim_ids"]
        got_claims = ([q.claim_id for q in res.rfi_followup.questions]
                      if res.rfi_followup else [])
        assert got_claims == want_claims, spec["role"]

    # --- the trace scored above IS the tamper-evident one ------------------ #
    for spec in _SUBJECTS:
        res = results[spec["role"]]
        stamped = [r for r in res.audit_records
                   if r["actor"] == "agency" and r["action"] == "decision"]
        assert len(stamped) == len(res.decisions), spec["role"]
        for record, rec in zip(stamped, res.decisions):
            assert json.loads(record["detail"]) == rec.summary(), spec["role"]
        assert res.audit_verified, spec["role"]


def test_agency_never_perturbs_the_sar(conn, trust_uid, tmp_path):
    """The published boundary, asserted: the surfaced runner-up advisory and
    the drafted follow-up RFI are analyst-facing only — the SAR narrative
    consumes the primary advisory alone and never references either effect."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    assert res.advisory is not None and res.secondary_advisory is not None

    sar_text = json.dumps(res.sar.model_dump(), default=str)
    assert res.advisory.advisory_id in sar_text
    assert res.secondary_advisory.advisory_id not in sar_text
    assert res.rfi_followup is not None
    for q in res.rfi_followup.questions:
        assert q.question not in sar_text


def test_gold_agency_version_matches_code():
    """The key was authored against this decision policy version; bumping the
    policy re-opens the key (mirroring the methodology anti-drift guard)."""
    from okojo.agency import AGENCY_VERSION

    assert _GOLD["agency_version"] == AGENCY_VERSION
