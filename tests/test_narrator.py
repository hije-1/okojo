"""Audit Narrator — unit tests over the located verifier and the narrator core.

Cheap and in-memory: chains are built with a fixed clock, mutated in place, and
narrated. The eval (test_narrator_eval.py) exercises the same machinery over the
REAL generated case chains.
"""

from __future__ import annotations

import json

import pytest

from okojo.audit import AuditLog, verify_records
from okojo.narrator import (
    NARRATOR_VERSION,
    AuditChainNarrative,
    NarrativeGroundingResolver,
    NarrativeSentence,
    RecordRef,
    assert_calibrated,
    assert_narrative_grounded,
    narrate_chain_batch,
    narrate_chain,
)
from okojo.sar.schema import CalibrationViolationError

_CLOCK = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731


def _chain(tmp_path, specs, name="c") -> AuditLog:
    log = AuditLog(tmp_path / f"{name}.jsonl", clock=_CLOCK)
    for actor, action, target, detail in specs:
        log.append(actor, action, target=target, detail=detail)
    return log


# --- the located verifier (Q10: additive, read-only) ----------------------- #
def test_verify_chain_located_good_and_parity(tmp_path):
    log = _chain(tmp_path, [("a", "act", None, f"d{i}") for i in range(3)])
    assert log.verify() is True
    v = log.verify_chain_located()
    assert v.ok and v.verified_count == 3 and v.break_seq is None and v.reason is None


def test_verify_chain_located_finds_break(tmp_path):
    log = _chain(tmp_path, [("a", "act", None, f"d{i}") for i in range(4)])
    recs = log.read_all()
    recs[2]["detail"] = "tampered"
    v = verify_records(recs)
    assert v.ok is False and v.break_seq == 3 and v.reason == "hash_mismatch"
    assert v.verified_count == 2
    # verify() stays the boolean face of the same check
    log.path.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    assert AuditLog(log.path).verify() is False


# --- narration ------------------------------------------------------------- #
def test_narrate_good_chain_two_register_grounded_calibrated(tmp_path):
    log = _chain(tmp_path, [
        ("orchestrator", "case_open", "uid:1", "Subj"),
        ("agency", "agency_config", None, json.dumps({"version": "1.5.0"})),
        ("profile_aggregator", "tool_call", "uid:1", None),
        ("profile_aggregator", "profile_built", "uid:1", "5 events, 1 anomalies"),
    ])
    records = log.read_all()
    nar = narrate_chain(records, family="case", subject="uid:1")

    assert nar.verified and nar.narrator_version == NARRATOR_VERSION
    assert len(nar.sentences) == len(records)
    # 1:1 — cited seqs are exactly the chain's seqs, in order
    assert [s.ref.seq for s in nar.sentences] == [r["seq"] for r in records]
    # two registers: config + tool_call de-emphasized
    assert [s.register for s in nar.sentences] == ["action", "setup", "setup", "action"]
    assert all(s.templated for s in nar.sentences)
    assert nar.sentences[0].ref.cite().startswith("record#1@")
    # idempotent — narrate_chain already asserted both
    assert_narrative_grounded(nar, records)
    assert_calibrated(nar)
    assert "  · Invoked the profile aggregator stage." in nar.plain()


def test_unknown_action_uses_generic_faithful_reading(tmp_path):
    log = _chain(tmp_path, [("mystery_actor", "mystery_action", "x", "stuff")])
    records = log.read_all()
    nar = narrate_chain(records)
    s = nar.sentences[0]
    assert s.templated is False
    assert "mystery actor" in s.text and "mystery action" in s.text and "stuff" in s.text
    assert_narrative_grounded(nar, records)  # a generic reading is still grounded


def test_break_report_only_on_tamper(tmp_path):
    log = _chain(tmp_path, [("a", "act", None, f"d{i}") for i in range(5)])
    records = log.read_all()
    target_seq = records[2]["seq"]
    records[2]["detail"] = (records[2].get("detail") or "") + " TAMPERED"

    nar = narrate_chain(records, family="case")
    assert nar.verified is False
    assert len(nar.sentences) == 1  # break-report-only: nothing past the break
    s = nar.sentences[0]
    assert s.register == "break"
    assert f"#{target_seq}" in s.text and "FAILED" in s.text and "withheld" in s.text.lower()
    # cites the broken record; the ref resolves against the chain as read
    assert NarrativeGroundingResolver(records).resolves(s.ref)


def test_calibration_guard_rejects_banned_terms():
    ref = RecordRef(1, "0" * 64)
    bad = AuditChainNarrative(
        "case", None, True, 1,
        [NarrativeSentence(ref, "action", "The agent autonomously determined guilt.")],
    )
    with pytest.raises(CalibrationViolationError):
        assert_calibrated(bad)


# --- sweep + batch (Slice 2) ----------------------------------------------- #
def _sweep_chain(tmp_path, name, did):
    return _chain(tmp_path, [
        ("remediation_sweep", "sweep_open", did,
         json.dumps({"designated_name": f"Party {name}", "list_type": "national_ct"})),
        ("remediation_sweep", "sweep_config", None, json.dumps({"version": "1.1.0"})),
        ("remediation_sweep", "exposure_sweep", did,
         json.dumps({"direct_uids": [1, 2], "adjacent_review_only_uids": [3]})),
        ("remediation_sweep", "sweep_complete", did,
         json.dumps({"exposed_accounts": 2, "name_matches": 1, "worksheet_rows": 4})),
    ], name=name).read_all()


def test_narrate_sweep_chain_two_register_grounded(tmp_path):
    records = _sweep_chain(tmp_path, "s1", "DES-2026-0001")
    nar = narrate_chain(records, family="sweep", subject="DES-2026-0001")
    assert nar.verified and [s.register for s in nar.sentences] == \
        ["action", "setup", "action", "action"]
    assert all(s.templated for s in nar.sentences)
    assert "Opened the remediation sweep for Party s1" in nar.sentences[0].text
    assert "2 directly exposed account(s)" in nar.sentences[2].text
    assert_narrative_grounded(nar, records)
    assert_calibrated(nar)


def test_narrate_chain_batch_rolls_up_constituents(tmp_path):
    a = _sweep_chain(tmp_path, "a", "DES-2026-0001")
    b = _sweep_chain(tmp_path, "b", "DES-2026-0002")
    bn = narrate_chain_batch([("DES-2026-0001", a), ("DES-2026-0002", b)])

    assert bn.designation_count == 2
    assert bn.narrator_version == NARRATOR_VERSION
    assert len(bn.rollup.sentences) == 2
    assert all("verified across 4 record(s)" in s.text for s in bn.rollup.sentences)
    # the roll-up grounds ONLY to real constituent records (never the rollup view)
    all_records = a + b
    assert_narrative_grounded(bn.rollup, all_records)
    resolver = NarrativeGroundingResolver(all_records)
    assert all(resolver.resolves(s.ref) for s in bn.rollup.sentences)
    # the batch plain rendering leads with the roll-up, then each chain
    assert bn.plain().startswith("Batch roll-up over 2 designation(s):")
