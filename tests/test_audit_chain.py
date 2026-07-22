"""The audit log is append-only and tamper-evident."""

from __future__ import annotations

from okojo.audit import AuditLog
from okojo.provenance import Provenance


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-01-01T00:00:{n['i']:02d}+00:00"

    return clock


def test_append_and_verify(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl", clock=_counter())
    log.append("orchestrator", "case_open", target="uid:1")
    log.append("profile_aggregator", "tool_call",
               provenance=Provenance(source="accounts", row_key="uid:1"))
    log.append("sar_drafter", "drafted", target="SAR-1")
    assert len(log.read_all()) == 3
    assert log.verify() is True


def test_tamper_breaks_chain(tmp_path):
    path = tmp_path / "b.jsonl"
    log = AuditLog(path, clock=_counter())
    log.append("a", "one")
    log.append("b", "two")
    log.append("c", "three")
    assert log.verify() is True

    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("two", "SILENTLY_EDITED")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert AuditLog(path, clock=_counter()).verify() is False


def test_deleted_record_breaks_chain(tmp_path):
    path = tmp_path / "c.jsonl"
    log = AuditLog(path, clock=_counter())
    for i in range(4):
        log.append("actor", f"action_{i}")
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # drop a record
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert AuditLog(path, clock=_counter()).verify() is False


def test_resume_existing_chain(tmp_path):
    path = tmp_path / "d.jsonl"
    log = AuditLog(path, clock=_counter())
    log.append("a", "one")
    # New handle resumes the chain rather than restarting seq/hash.
    log2 = AuditLog(path, clock=_counter())
    rec = log2.append("b", "two")
    assert rec["seq"] == 2
    assert log2.verify() is True
