"""COVERAGE Slice C2 — the assessment's own chain family, narrated.

The coverage assessment writes its OWN hash-chained trail under ``data/coverage/``
— a new chain family alongside case / sweep — and the narrator summarizes it
faithfully. This eval pins:

* **The chain** — ``run_coverage_audit`` writes a verifying chain whose record
  vocabulary is EXACTLY ``COVERAGE_TEMPLATES`` (the Phase-9 coverage guarantee:
  every record type templated, none falling back to the generic reading).
* **Narration** — narrating the chain over the ``coverage`` family verifies, is
  fully templated, grounded, and calibrated; the sentence order matches the
  record order.
* **Finding parity** — the finding record's covered / gap sets equal the answer
  key (the chain reports what the assessment concluded).
* **Isolation** — the run writes only under its own out_dir; the frozen registry
  is never mutated.
* **Tamper** — a mutated chain is reported AS the narrative (the break located
  and cited), nothing summarized past it.
* **P8-G** — flipping the UN backstop to ingested (injected copy) changes the
  finding record's gap set.
"""

from __future__ import annotations

import copy
import json

from okojo.audit import AuditLog
from okojo.coverage import run_coverage_audit
from okojo.narrator.narrator import (
    COVERAGE_TEMPLATES,
    NarrativeGroundingResolver,
    assert_calibrated,
    assert_narrative_grounded,
    narrate_chain,
)
from okojo.sweep import LIST_SOURCE_REGISTRY

_CLOCK = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731


def _finding(records: list[dict]) -> dict:
    rec = next(r for r in records
               if (r["actor"], r["action"]) == ("coverage_assessment", "coverage_finding"))
    return json.loads(rec["detail"])


# ---- the chain -------------------------------------------------------------- #

def test_coverage_chain_verifies_and_is_fully_templated(conn, tmp_path):
    res = run_coverage_audit(conn, out_dir=tmp_path / "coverage", audit_clock=_CLOCK)
    assert res.audit_verified
    observed = {(r["actor"], r["action"]) for r in res.audit_records}
    # Phase-9 coverage guarantee: observed vocabulary == the registry, exactly.
    assert observed == set(COVERAGE_TEMPLATES), (
        observed.symmetric_difference(set(COVERAGE_TEMPLATES)))


def test_coverage_chain_record_count_is_exactly_five(conn, tmp_path):
    """E-C: a coverage run stamps exactly five records (open, config, footprint,
    finding, complete) — a new family, no existing chain touched."""
    res = run_coverage_audit(conn, out_dir=tmp_path / "coverage", audit_clock=_CLOCK)
    assert len(res.audit_records) == 5


def test_run_writes_only_under_its_out_dir(conn, tmp_path):
    out = tmp_path / "coverage"
    run_coverage_audit(conn, out_dir=out, audit_clock=_CLOCK)
    assert (out / "audit_log.jsonl").exists()
    # Nothing written outside the out_dir (only the chain file is produced).
    assert sorted(p.name for p in out.iterdir()) == ["audit_log.jsonl"]


# ---- narration -------------------------------------------------------------- #

def test_coverage_chain_narrates_faithfully(conn, tmp_path):
    res = run_coverage_audit(conn, out_dir=tmp_path / "coverage", audit_clock=_CLOCK)
    nar = narrate_chain(res.audit_records, family="coverage")
    assert nar.verified
    assert nar.record_count == len(res.audit_records)
    assert [s.ref.seq for s in nar.sentences] == [r["seq"] for r in res.audit_records]
    fell_back = [s.text for s in nar.sentences if not s.templated]
    assert not fell_back, fell_back
    assert_narrative_grounded(nar, res.audit_records)
    assert_calibrated(nar)
    # The one setup record is the policy stamp; the rest are consequential.
    setup = [s for s in nar.sentences if s.register == "setup"]
    assert len(setup) == 1


# ---- finding parity --------------------------------------------------------- #

def test_finding_record_matches_answer_key(conn, tmp_path, ground_truth):
    res = run_coverage_audit(conn, out_dir=tmp_path / "coverage", audit_clock=_CLOCK)
    f = _finding(res.audit_records)
    assert f["covered"] == sorted(ground_truth["coverage_covered_jurisdictions"])
    assert f["ingestion_gaps"] == sorted(ground_truth["coverage_ingestion_gaps"])
    assert f["no_coverage_gaps"] == sorted(ground_truth["coverage_no_coverage_gaps"])
    assert f["declared_not_ingested_regimes"] == sorted(
        ground_truth["coverage_declared_not_ingested_regimes"])


# ---- tamper ----------------------------------------------------------------- #

def test_tampered_coverage_chain_reported_as_narrative(conn, tmp_path):
    res = run_coverage_audit(conn, out_dir=tmp_path / "coverage", audit_clock=_CLOCK)
    path = res.audit_log_path
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    idx = len(records) // 2
    target_seq = records[idx]["seq"]
    records[idx]["detail"] = (records[idx].get("detail") or "") + " TAMPERED"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    assert AuditLog(path).verify() is False
    nar = narrate_chain(path, family="coverage")
    assert nar.verified is False
    assert len(nar.sentences) == 1
    s = nar.sentences[0]
    assert s.register == "break" and f"#{target_seq}" in s.text and "withheld" in s.text.lower()
    assert NarrativeGroundingResolver(records).resolves(s.ref)


# ---- P8-G ------------------------------------------------------------------- #

def test_p8g_registry_flip_changes_the_finding_record(conn, tmp_path):
    base = run_coverage_audit(conn, out_dir=tmp_path / "c0", audit_clock=_CLOCK)
    assert _finding(base.audit_records)["ingestion_gaps"]

    reg = copy.deepcopy(dict(LIST_SOURCE_REGISTRY))
    reg["SYN-UN-CONSOLIDATED"]["ingested"] = True
    flipped = run_coverage_audit(conn, out_dir=tmp_path / "c1",
                                 audit_clock=_CLOCK, list_source_registry=reg)
    assert _finding(flipped.audit_records)["ingestion_gaps"] == []
    assert LIST_SOURCE_REGISTRY["SYN-UN-CONSOLIDATED"]["ingested"] is False
