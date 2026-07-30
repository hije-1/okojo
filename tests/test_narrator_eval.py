"""Audit Narrator eval — grounding P/R over planted chains + real-chain coverage.

Four checks, in the P8-A / P8-G discipline:
  * grounding P/R/F1 vs a domain-authored gold over planted CASE chains, plus
    per-record register + faithful-keyword assertions;
  * coverage over the REAL generated case chains (every record narrates, is
    templated, grounds, and calibrates; cited seqs == chain seqs);
  * a TAMPERED real chain reported as the narrative (break at the correct seq);
  * an ungrounded-sentence injection shown silent-without / rejected-with the
    grounding guard (P8-G falsification).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from okojo.audit import AuditLog
from okojo.eval import score
from okojo.narrator import (
    AuditChainNarrative,
    NarrativeGroundingError,
    NarrativeGroundingResolver,
    NarrativeSentence,
    RecordRef,
    assert_calibrated,
    assert_narrative_grounded,
    narrate_chain,
)
from okojo.orchestrator import run_case

_GOLD = json.loads(
    (Path(__file__).parent / "data" / "narrator_case_gold.json").read_text(encoding="utf-8")
)
_CLOCK = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731


def _build(spec, tmp_path) -> list[dict]:
    log = AuditLog(tmp_path / f"{spec['name']}.jsonl", clock=_CLOCK)
    for r in spec["records"]:
        detail = json.dumps(r["detail_obj"]) if "detail_obj" in r else r.get("detail")
        log.append(r["actor"], r["action"], target=r.get("target"), detail=detail)
    return log.read_all()


def test_narrator_grounding_scorecard(tmp_path, capsys):
    predicted: set[tuple] = set()
    gold: set[tuple] = set()
    lines = []
    for spec in _GOLD["chains"]:
        records = _build(spec, tmp_path)
        nar = narrate_chain(records, family="case", subject=spec["subject"])
        assert nar.verified
        assert len(nar.sentences) == len(records)

        resolver = NarrativeGroundingResolver(records)
        for s in nar.sentences:
            if resolver.resolves(s.ref):
                predicted.add((spec["name"], s.ref.seq))
        for r in records:
            gold.add((spec["name"], int(r["seq"])))

        # domain-authored per-record expectations: right record, right register,
        # a faithful sentence (independently authored keywords), templated.
        for exp, s, r in zip(spec["expected"], nar.sentences, records):
            assert s.ref.seq == int(r["seq"]), (spec["name"], r["action"])
            assert s.register == exp["register"], (spec["name"], r["action"])
            assert s.templated, (spec["name"], r["action"])
            for kw in exp["must_include"]:
                assert kw in s.text, (spec["name"], r["action"], kw, s.text)
        lines.append(f"  {spec['name']:22s} {len(records):2d} records, all grounded + templated")

    result = score(predicted, gold)
    with capsys.disabled():
        print("\nAudit-Narrator grounding scorecard (planted case chains, "
              "domain-authored gold):")
        for ln in lines:
            print(ln)
        print(f"  narrator_grounding: {result}")
    assert result.precision == 1.0 and result.recall == 1.0 and result.f1 == 1.0


def test_narrator_covers_real_case_chains(conn, trust_uid, ring, tmp_path):
    """Every record an actual generated case chain emits is narrated by a
    specific template (no generic fallback) — the registry covers the full
    case vocabulary."""
    for label, uid in (("trust", trust_uid), ("recidivist", ring["RECIDIVIST"])):
        res = run_case(uid, conn=conn, out_dir=tmp_path / f"c{uid}", render_graph=False)
        nar = narrate_chain(res.audit_log_path, family="case", subject=f"uid:{uid}")

        assert nar.verified, label
        assert nar.record_count == len(res.audit_records), label
        assert len(nar.sentences) == len(res.audit_records), label
        # 1:1 — cited seqs are exactly the chain's seqs, in order
        assert [s.ref.seq for s in nar.sentences] == [r["seq"] for r in res.audit_records], label
        fell_back = [s.text for s in nar.sentences if not s.templated]
        assert not fell_back, (label, fell_back)
        assert_narrative_grounded(nar, res.audit_records)
        assert_calibrated(nar)


def test_tampered_real_chain_reported_as_narrative(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "c", render_graph=False)
    path = res.audit_log_path
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    idx = len(records) // 2
    target_seq = records[idx]["seq"]
    records[idx]["detail"] = (records[idx].get("detail") or "") + " TAMPERED"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    # independent verification locates the break
    log = AuditLog(path)
    assert log.verify() is False
    v = log.verify_chain_located()
    assert v.break_seq == target_seq and v.reason == "hash_mismatch"

    # the narrative IS the break report; nothing at or past the break is summarized
    nar = narrate_chain(path, family="case")
    assert nar.verified is False
    assert len(nar.sentences) == 1
    s = nar.sentences[0]
    assert s.register == "break" and f"#{target_seq}" in s.text and "withheld" in s.text.lower()
    assert NarrativeGroundingResolver(records).resolves(s.ref)


def test_ungrounded_injection_falsification(tmp_path):
    """P8-G: a fabricated citation is invisible without the guard, rejected with it."""
    spec = _GOLD["chains"][0]
    records = _build(spec, tmp_path)
    nar = narrate_chain(records, family="case")
    bogus = NarrativeSentence(RecordRef(999999, "de" * 32), "action",
                              "Injected ungrounded claim.")
    injected = AuditChainNarrative(nar.family, nar.subject, nar.verified,
                              nar.record_count, nar.sentences + [bogus])

    # RED — without the guard the fabricated citation simply sits in the narrative
    assert not NarrativeGroundingResolver(records).resolves(bogus.ref)
    assert bogus in injected.sentences
    # GREEN — the guard rejects it fail-closed
    with pytest.raises(NarrativeGroundingError):
        assert_narrative_grounded(injected, records)
