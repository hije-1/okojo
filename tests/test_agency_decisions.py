"""Phase 6: the five bounded decision rules, positive and negative branches.

Every rule is a pure function of explicit evidence values — these tests
exercise both sides of each gate on synthetic arguments (including branches
the planted scenario never takes, e.g. the insufficient-evidence referral),
plus the graph-level behaviour of the decision effects on a live case run.
The full per-subject decision-trace eval against the committed expected-
decision key lives in test_decision_trace_eval.py.
"""

from __future__ import annotations

import json

from okojo.agency import (
    DECISION_OUTCOMES,
    decide_expand,
    decide_re_rfi,
    decide_sar_bar,
    decide_second_advisory,
    decide_sufficiency,
    draft_followup,
)
from okojo.orchestrator import run_case
from okojo.orchestrator.graph import _human_referral
from okojo.audit import AuditLog
from okojo.rfi import check_contradictions, decompose
from okojo.entity import build_backbone


# --- D1 expand_hop -----------------------------------------------------------

def test_expand_continues_while_frontier_productive():
    rec = decide_expand(hops_done=1, cap=2, new_accounts_last_hop=7)
    assert rec.outcome == "continue"
    assert rec.evidence == {"hops_done": 1, "cap": 2, "new_accounts_last_hop": 7}


def test_expand_stops_at_cap_even_with_new_accounts():
    assert decide_expand(hops_done=2, cap=2, new_accounts_last_hop=4).outcome == "stop_cap"


def test_expand_stops_on_exhausted_frontier():
    rec = decide_expand(hops_done=1, cap=2, new_accounts_last_hop=0)
    assert rec.outcome == "stop_frontier_exhausted"


# --- D2 second_advisory ------------------------------------------------------

class _FakeMatch:
    def __init__(self, advisory_id: str):
        self.advisory_id = advisory_id


def test_second_advisory_pulled_only_with_two_survivors():
    two = [_FakeMatch("A-1"), _FakeMatch("A-2")]
    assert decide_second_advisory(two).outcome == "pull_second"
    assert decide_second_advisory(two[:1]).outcome == "single_match"
    assert decide_second_advisory([]).outcome == "no_match"


# --- D3 re_rfi ---------------------------------------------------------------

def test_re_rfi_not_applicable_without_rfi():
    assert decide_re_rfi(None).outcome == "not_applicable"


def test_re_rfi_recommended_only_on_contradicted_claims(conn, trust_uid, ground_truth):
    backbone = build_backbone(conn)
    table = check_contradictions(
        conn, trust_uid, backbone, decomposition=decompose(conn, trust_uid),
    )
    rec = decide_re_rfi(table)
    assert rec.outcome == "recommend_re_rfi"
    # evidence names the contradicted claims — the flag verdicts only
    lies = {l["claim_id"] for l in ground_truth["rfi_lies"]}
    assert set(rec.evidence["claim_ids"]) == lies

    # strip the contradicted rows: qualified/unverifiable alone never trigger
    table.adjudications = [a for a in table.adjudications if not a.is_contradiction]
    assert decide_re_rfi(table).outcome == "no_contradictions"


def test_followup_drafts_one_question_per_contradicted_claim(conn, trust_uid):
    backbone = build_backbone(conn)
    table = check_contradictions(
        conn, trust_uid, backbone, decomposition=decompose(conn, trust_uid),
    )
    followup = draft_followup(table)
    assert followup.rfi_id == table.rfi_id
    assert [q.claim_id for q in followup.questions] == [
        a.claim_id for a in table.contradictions
    ]
    for q, adj in zip(followup.questions, table.contradictions):
        # the question restates the subject's own assertion and cites both the
        # rebuttal surfaces and their provenance
        assert adj.claim_text in q.question
        assert q.sources == adj.sources
        assert q.citations and all(q.citations)


# --- D4 sufficiency ----------------------------------------------------------

def test_sufficiency_requires_subject_and_one_event():
    assert decide_sufficiency(True, 9).outcome == "sufficient"
    assert decide_sufficiency(True, 1).outcome == "sufficient"
    assert decide_sufficiency(True, 0).outcome == "insufficient"
    assert decide_sufficiency(False, 9).outcome == "insufficient"


def test_human_referral_node_flags_and_never_drafts(tmp_path):
    """The negative branch of the sufficiency gate: an audit stamp naming the
    disposition, sar=None, and nothing fabricated."""
    audit = AuditLog(tmp_path / "audit.jsonl")
    update = _human_referral({"audit": audit, "subject_uid": 999})
    assert update == {"sar": None, "critique_history": None}
    records = audit.read_all()
    assert len(records) == 1
    assert (records[0]["actor"], records[0]["action"]) == ("orchestrator", "human_referral")
    detail = json.loads(records[0]["detail"])
    assert detail["disposition"] == "insufficient_evidence"
    assert audit.verify()


# --- D5 sar_bar --------------------------------------------------------------

def test_sar_bar_follows_critic_convergence(conn, trust_uid, tmp_path):
    trust = run_case(trust_uid, conn=conn, out_dir=tmp_path / "t", render_graph=False)
    rec = decide_sar_bar(trust.critique_history)
    assert rec.outcome == "clears_bar"
    assert rec.evidence["converged"] is True

    noise_uid = max(a["uid"] for a in conn.all_accounts())  # a peripheral account
    noise = run_case(noise_uid, conn=conn, out_dir=tmp_path / "n", render_graph=False)
    rec = decide_sar_bar(noise.critique_history)
    assert rec.outcome == "human_review"
    assert rec.evidence["flagged"], "unmet rubric elements must be named"


# --- graph-level behaviour on the live scenario ------------------------------

def test_trust_case_decision_effects(conn, trust_uid, ground_truth, tmp_path):
    """On the trust case every decision effect is live: a runner-up advisory is
    surfaced (never drafted), a follow-up RFI is drafted (never sent), and the
    decision ids appear in trace order."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)

    assert [d.decision_id for d in res.decisions] == [
        "expand_hop", "expand_hop", "second_advisory", "re_rfi",
        "sufficiency", "sar_bar",
    ]

    # the runner-up advisory is surfaced but the SAR consumed the primary only
    assert res.secondary_advisory is not None
    assert res.advisory is not None
    assert res.secondary_advisory.advisory_id != res.advisory.advisory_id

    # the drafted follow-up covers exactly the ground-truth lies
    lies = {l["claim_id"] for l in ground_truth["rfi_lies"]}
    assert res.rfi_followup is not None
    assert {q.claim_id for q in res.rfi_followup.questions} == lies

    # closed outcome sets: every recorded outcome is a declared one
    for d in res.decisions:
        assert d.outcome in DECISION_OUTCOMES[d.decision_id]
