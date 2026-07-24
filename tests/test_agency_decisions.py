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
    TippingOffRisk,
    assert_no_tipping_off,
    decide_expand,
    decide_re_rfi,
    decide_sar_bar,
    decide_second_advisory,
    decide_sufficiency,
    draft_followup,
)
from okojo.entity import build_backbone, name_tokens
from okojo.orchestrator import run_case
from okojo.orchestrator.graph import _human_referral
from okojo.audit import AuditLog
from okojo.provenance import Provenance
from okojo.rfi import ContradictionTable, check_contradictions, decompose
from okojo.rfi.checkers import Rebuttal
from okojo.rfi.contradiction import ClaimAdjudication


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


def _trust_followup(conn, trust_uid):
    backbone = build_backbone(conn)
    table = check_contradictions(
        conn, trust_uid, backbone, decomposition=decompose(conn, trust_uid),
    )
    return table, draft_followup(table)


def test_followup_prepares_discrete_requests_per_claim(conn, trust_uid):
    """One worklist entry per contradicted claim; requests are discrete,
    standalone routine asks — never a pre-assembled letter."""
    table, followup = _trust_followup(conn, trust_uid)
    assert followup.rfi_id == table.rfi_id
    assert [q.claim_id for q in followup.questions] == [
        a.claim_id for a in table.contradictions
    ]
    for q, adj in zip(followup.questions, table.contradictions):
        assert q.sources == adj.sources          # analyst metadata preserved
        assert q.suppressed == []                # nothing tripped the screen
        for r in q.requests:
            assert r.citations and all(r.citations)

    # C2 (onchain + prior_rfi + registry) carries all three request kinds;
    # C4 (onchain only) carries exactly the transaction-records ask.
    by_claim = {q.claim_id: q for q in followup.questions}
    assert {r.kind for r in by_claim["C2"].requests} == {
        "transactions", "corporate_records", "prior_response"}
    assert [r.kind for r in by_claim["C4"].requests] == ["transactions"]


def test_followup_onchain_cites_only_the_subjects_own_transactions(conn, trust_uid):
    """The transaction ask names the exact tx rows from the rebuttal evidence
    and never cites gas-funding / address-attribution rows (tracing focus)."""
    table, followup = _trust_followup(conn, trust_uid)
    by_claim = {q.claim_id: q for q in followup.questions}
    for adj in table.contradictions:
        onchain = [r for r in adj.rebuttals if r.source == "onchain"]
        tx_ids = {p.row_key for r in onchain for p in r.provenance
                  if p.source == "transactions"}
        other_rows = {p.row_key for r in onchain for p in r.provenance
                      if p.source != "transactions"}
        tx_req = next(r for r in by_claim[adj.claim_id].requests
                      if r.kind == "transactions")
        for tx_id in tx_ids:
            assert tx_id in tx_req.text
        for row in other_rows:
            assert row not in tx_req.text


def test_followup_never_names_a_ring_entity(conn, trust_uid):
    """The corporate-records ask deliberately does NOT name the denied entity
    — no request text may contain any ring entity's distinctive name tokens
    (the subject's inclusion or omission of the agreement is the signal)."""
    _, followup = _trust_followup(conn, trust_uid)
    ring_tokens = set()
    for a in conn.all_accounts():
        if a["role_in_ring"] != "noise":
            ring_tokens.update(name_tokens(a["entity_name"]))
    for q in followup.questions:
        for r in q.requests:
            low = r.text.lower()
            for tok in ring_tokens:
                assert tok not in low, (q.claim_id, r.kind, tok)


def test_followup_prior_response_quotes_their_own_reference(conn, trust_uid, ground_truth):
    """The prior-RFI ask quotes the subject's own earlier response by its
    reference id (their words are disclosable; our cross-referencing is not)."""
    _, followup = _trust_followup(conn, trust_uid)
    prior_reqs = [r for q in followup.questions for r in q.requests
                  if r.kind == "prior_response"]
    assert prior_reqs, "C2's prior-RFI leg must yield a request"
    for r in prior_reqs:
        assert any(pid in r.text for pid in ground_truth["prior_rfi_ids"])
        assert "In your response to" in r.text


def test_device_only_contradiction_yields_no_subject_request():
    """Device linkage is internal capability — a claim rebutted ONLY by device
    evidence generates zero subject-facing requests (and is not 'suppressed';
    it is policy-excluded)."""
    adj = ClaimAdjudication(
        claim_id="CX", claim_text="No third party operates this account.",
        verdict="contradicted", confidence=0.9,
        provenance=Provenance(source="rfi", row_key="SIM-RFI-9999"),
        rebuttals=[Rebuttal(
            source="device",
            statement="a shared device fingerprint links the account to another",
            strength=0.9,
            provenance=[Provenance(source="devices", row_key="fp:abc")],
        )],
    )
    table = ContradictionTable(rfi_id="SIM-RFI-9999", uid=1, adjudications=[adj])
    followup = draft_followup(table)
    assert followup.questions[0].requests == []
    assert followup.questions[0].suppressed == []
    assert followup.questions[0].sources == ["device"]


# --- anti-tipping-off guardrail (subject-facing text only) -------------------

def test_all_live_requests_pass_the_tipping_off_screen(conn, trust_uid):
    """Positive calibration: every request the live scenario generates passes
    the validator (the approved neutral templates must remain clean)."""
    _, followup = _trust_followup(conn, trust_uid)
    rendered = [r.text for q in followup.questions for r in q.requests]
    assert rendered
    for text in rendered:
        assert_no_tipping_off(text)  # must not raise


def test_tipping_off_screen_catches_dangerous_phrasings():
    """Negative cases: review/reporting status, evidence surfaces, methods,
    and typology terms are all caught — on fully rendered text."""
    import pytest

    dangerous = [
        "This transaction was flagged as suspicious and reported in a SAR.",
        "Our compliance investigation found your account under review.",
        "On-chain evidence is inconsistent with your statement.",
        "Your device fingerprint matches another account.",
        "These structured transfers suggest layering through shell entities.",
        "Records indicate exposure to sanctioned Iranian oil smuggling.",
        "See FinCEN advisory FIN-2025-A002.",
        # interpolation smuggling: neutral template + poisoned value
        "In your response to SIM-RFI-0000, a sanctions evasion agreement was "
        "referenced. Please provide a copy of that agreement.",
    ]
    for text in dangerous:
        with pytest.raises(TippingOffRisk):
            assert_no_tipping_off(text)


def test_admission_is_fail_closed():
    """A dangerous rendered request is suppressed and flagged for human
    authoring — never emitted. (Direct test of the admission helper.)"""
    from okojo.agency.decisions import _admit

    requests, suppressed = [], []
    _admit(requests, suppressed, kind="transactions",
           text="We flagged suspicious transfers to sanctioned wallets.",
           citations=["transactions[SIMTX000000]"])
    assert requests == []
    assert suppressed == ["transactions"]


def test_poisoned_extraction_falls_back_to_generic_phrase():
    """If the quotable phrase extracted from evidence would smuggle a banned
    term into the rendered request, the generic phrase is used instead."""
    adj = ClaimAdjudication(
        claim_id="CY", claim_text="We deny any relationship with that entity.",
        verdict="contradicted", confidence=0.9,
        provenance=Provenance(source="rfi", row_key="SIM-RFI-9998"),
        rebuttals=[Rebuttal(
            source="prior_rfi",
            statement="the earlier answer concedes a sanctions evasion agreement",
            strength=0.9,
            provenance=[Provenance(source="rfi_prior", row_key="SIM-RFI-0000")],
        )],
    )
    table = ContradictionTable(rfi_id="SIM-RFI-9998", uid=1, adjudications=[adj])
    followup = draft_followup(table)
    reqs = followup.questions[0].requests
    assert len(reqs) == 1 and reqs[0].kind == "prior_response"
    assert "sanction" not in reqs[0].text.lower()
    assert "an arrangement bearing on this matter" in reqs[0].text
    assert_no_tipping_off(reqs[0].text)


def test_plain_language_on_every_decision(conn, trust_uid, tmp_path):
    """Every decision carries a non-empty, ASCII plain-language gloss (it is
    stamped into the chain and packaged, so it must be audit-safe)."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    assert res.decisions
    for d in res.decisions:
        assert d.plain_language.strip()
        assert d.plain_language.isascii()


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
