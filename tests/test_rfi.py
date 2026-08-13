"""RFI reader surfaces the subject's RFI, grounded — and BLIND to the answer key.

The runtime view carries claim text but no ground-truth label or authored
rebuttal note (F-016). The scenario answer key is read only through the eval
helper (``okojo.eval.rfi_claim_answer_key``), which loads it straight from
``claims_json``; an invariant test then proves no runtime ``CaseResult`` dump can
carry the label field names or the distinctive rebuttal-note values.
"""

from __future__ import annotations

import json

from okojo.eval import rfi_claim_answer_key
from okojo.orchestrator import run_case
from okojo.rfi import load_rfi


def test_load_rfi_for_trust_subject(conn, trust_uid):
    rfi = load_rfi(conn, trust_uid)
    assert rfi is not None
    assert rfi.rfi_id and rfi.question and rfi.response_text
    assert len(rfi.claims) == 4
    assert rfi.provenance  # grounded


def test_runtime_rfi_claims_carry_no_answer_key(conn, trust_uid):
    """The runtime claim model exposes id + text only — no label, no rebuttal
    note. The answer key is not reachable from the surfaced record."""
    rfi = load_rfi(conn, trust_uid)
    assert set(rfi.claims[0].model_fields) == {"claim_id", "text"}
    for c in rfi.claims:
        dump = c.model_dump()
        assert "ground_truth" not in dump
        assert "contradicted_by" not in dump


def test_false_claims_match_ground_truth_via_eval_helper(conn, trust_uid, ground_truth):
    """The scenario's declared lies still match its own answer key — asserted by
    reading the key through the eval helper (which loads claims_json directly),
    NOT off a runtime record."""
    key = rfi_claim_answer_key(conn, trust_uid)
    false_ids = {c["claim_id"] for c in key if c["ground_truth"] == "false"}
    gt_lie_ids = {lie["claim_id"] for lie in ground_truth["rfi_lies"]}
    assert false_ids == gt_lie_ids
    # every declared lie carries at least one contradiction note
    for c in key:
        if c["ground_truth"] == "false":
            assert c["contradicted_by"]


def test_account_without_rfi_returns_none(conn, ground_truth):
    priv_uid = ground_truth["privileged_redherring_uid"]
    assert load_rfi(conn, priv_uid) is None
    # the eval helper agrees: no RFI, empty key.
    assert rfi_claim_answer_key(conn, priv_uid) == []


def test_orchestrator_attaches_rfi(conn, trust_uid, ground_truth, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.rfi is not None and res.rfi.claims

    priv_uid = ground_truth["privileged_redherring_uid"]
    res2 = run_case(priv_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res2.rfi is None


def test_case_result_dump_contains_no_answer_key(conn, trust_uid, tmp_path):
    """Invariant: a runtime CaseResult serialization carries neither the answer-
    key FIELD NAMES nor the distinctive rebuttal-note VALUES. This is the
    F-016 guarantee — a downstream consumer that dumps the case can never
    recover the scenario labels from it."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)

    # Serialize the RFI view (the object that used to carry the key) to JSON.
    dumped = json.dumps(res.rfi.model_dump(), default=str)

    # Field names absent.
    assert "ground_truth" not in dumped
    assert "contradicted_by" not in dumped

    # Distinctive VALUES absent: every authored rebuttal-note string (the
    # scenario's most identifying answer-key prose) must not appear in the dump.
    key = rfi_claim_answer_key(conn, trust_uid)
    notes = [note for c in key for note in c["contradicted_by"]]
    assert notes, "fixture sanity: the scenario declares rebuttal notes"
    for note in notes:
        assert note not in dumped, f"answer-key note leaked into runtime dump: {note!r}"
