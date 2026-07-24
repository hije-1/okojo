"""Phase 5 eval — the RFI Contradiction-Checker, scored against the answer key.

Three scorecards ship with the capability (discipline rule: every capability
ships its eval), printed under ``capsys.disabled()`` like the phase-2, advisory
and SAR scorecards:

1. **Contradiction detection P/R/F1.** The positive class is strictly
   *adjudicated ``contradicted``*. ``qualified`` and ``unverifiable`` are
   correct non-positive outcomes, not false positives — a false positive is a
   claim escalated all the way to ``contradicted``. The four-verdict table is
   printed alongside so the distinction is visible rather than implied.
2. **Verdict + rebuttal-source discrimination, all four claims.** Every claim's
   verdict and the exact set of probes that fired must equal the key. Covering
   all four exercises every adjudication branch, including ``qualified``, which
   the detection scorecard alone would never reach.
3. **One-list-three-consumers invariant.** The claim's ``contradicted_by``
   prose, the key's ``expected_sources``, and the probes that actually fire all
   trace to one definition. Slices A and B pinned the first two; this closes the
   third, which is the consumer that only exists once the checkers do.

The system under test never sees any of this: the checkers read evidence tables
only (``tests/test_rfi_checkers.py`` asserts that against their source).
"""

from __future__ import annotations

from okojo.entity import build_backbone
from okojo.eval import score
from okojo.rfi import check_contradictions
from okojo.scenario.generator import _RFI_CLAIM_SOURCES, _notes_for, _sources_for


def _table(conn, trust_uid):
    return check_contradictions(conn, trust_uid, build_backbone(conn))


def _key(ground_truth) -> dict:
    return {k["claim_id"]: k for k in ground_truth["rfi_claim_key"]}


# --------------------------------------------------------------------------- #
# 1) Contradiction-detection scorecard
# --------------------------------------------------------------------------- #
def test_contradiction_detection_scorecard(conn, trust_uid, ground_truth, capsys):
    table = _table(conn, trust_uid)
    key = _key(ground_truth)

    predicted = {a.claim_id for a in table.adjudications if a.verdict == "contradicted"}
    gold = {cid for cid, k in key.items() if k["verdict"] == "contradicted"}
    result = score(predicted, gold)

    with capsys.disabled():
        print("\nRFI contradiction-detection scorecard (positive class = 'contradicted'):")
        print(f"  {'claim':6s} {'verdict':14s} {'gold':14s} {'conf':>5s}  sources")
        for a in table.adjudications:
            k = key[a.claim_id]
            flag = "" if a.verdict == k["verdict"] else "   <-- MISMATCH"
            print(f"  {a.claim_id:6s} {a.verdict:14s} {k['verdict']:14s} "
                  f"{a.confidence:5.2f}  {a.sources}{flag}")
        print(f"  detection: {result}")
        print("  note: 'qualified' and 'unverifiable' are correct non-positive")
        print("        outcomes; only an escalation to 'contradicted' is a false positive.")

    assert result.precision == 1.0 and result.recall == 1.0 and result.f1 == 1.0
    # The declared lies are exactly the positive class.
    assert gold == {lie["claim_id"] for lie in ground_truth["rfi_lies"]}


# --------------------------------------------------------------------------- #
# 2) Verdict + rebuttal-source discrimination
# --------------------------------------------------------------------------- #
def test_verdict_and_source_discrimination_scorecard(conn, trust_uid, ground_truth, capsys):
    table = _table(conn, trust_uid)
    key = _key(ground_truth)

    verdict_hits = 0
    source_hits = 0
    rows = []
    for a in table.adjudications:
        k = key[a.claim_id]
        v_ok = a.verdict == k["verdict"]
        s_ok = a.sources == k["expected_sources"]
        verdict_hits += v_ok
        source_hits += s_ok
        rows.append((a.claim_id, a.verdict, k["verdict"], a.sources,
                     k["expected_sources"], v_ok, s_ok))

    n = len(table.adjudications)
    with capsys.disabled():
        print("\nRFI verdict + rebuttal-source discrimination (all four claims):")
        for cid, got_v, want_v, got_s, want_s, v_ok, s_ok in rows:
            print(f"  {cid}  verdict {got_v:14s} (expect {want_v:14s}) {'OK' if v_ok else 'FAIL'}")
            print(f"      sources {str(got_s):40s} (expect {want_s}) {'OK' if s_ok else 'FAIL'}")
        print(f"  verdict_accuracy: {verdict_hits}/{n}")
        print(f"  source_accuracy : {source_hits}/{n}")
        print(f"  branches exercised: {sorted({r[1] for r in rows})}")

    assert verdict_hits == n
    assert source_hits == n
    # Every adjudication branch the key specifies is actually reached.
    assert {r[1] for r in rows} == {"contradicted", "qualified", "unverifiable"}


def test_unverifiable_claim_draws_no_rebuttals(conn, trust_uid):
    """The precision control: nothing in the evidence speaks to C3, so nothing fires."""
    c3 = _table(conn, trust_uid).get("C3")
    assert c3.verdict == "unverifiable"
    assert c3.rebuttals == []
    assert c3.confidence == 0.0


# --------------------------------------------------------------------------- #
# 3) One-list-three-consumers invariant — now closing all three
# --------------------------------------------------------------------------- #
def test_one_list_three_consumers_invariant(conn, trust_uid, ground_truth, capsys):
    table = _table(conn, trust_uid)
    key = _key(ground_truth)

    rows = []
    for cid in ["C1", "C2", "C3", "C4"]:
        definition = _sources_for(cid)                 # the single definition
        expected = key[cid]["expected_sources"]        # consumer 2: the answer key
        fired = table.get(cid).sources                 # consumer 3: the checkers
        prose = len(_notes_for(cid))                   # consumer 1: contradicted_by
        rows.append((cid, definition, expected, fired, prose))

    with capsys.disabled():
        print("\nOne-list-three-consumers invariant (definition -> key -> checkers):")
        for cid, definition, expected, fired, prose in rows:
            print(f"  {cid}  definition={definition}")
            print(f"      key={expected}  checkers={fired}  contradicted_by_notes={prose}")

    for cid, definition, expected, fired, prose in rows:
        assert expected == definition, cid
        assert fired == definition, cid
        # The prose is generated from the same tuples, so its length must match
        # the number of (source, note) pairs declared for the claim.
        assert prose == len(_RFI_CLAIM_SOURCES[cid]), cid
