"""Reviewer disposition — a human decision written INTO the case hash chain (v1).

The feature: when a human reviews the finished case package, their decision is
appended to the same tamper-evident chain as the agent's work. In the public
demo the append lands in a *session-local sandbox* copy of the chain; the
canonical bytes on disk are never touched.

There is no gold key — a human decision has no predetermined correct answer.
These are invariant tests instead:

  (i)   rationale required — an empty rationale cannot produce a record;
  (ii)  the session chain re-verifies after append (single + repeated);
  (iii) the canonical on-disk chain is byte-identical after any number of
        sandbox dispositions;
  (iv)  the narrator line for the new record type is grounded and calibrated;
  (v)   falsification — break one of these deliberately, then restore.

The AppTest coverage for the "Reviewer decision" panel lives in
``test_case_ui.py`` (the module-scoped case app is the reliable render tool).
"""

from __future__ import annotations

import pytest

from okojo.audit import (
    AuditLog,
    DispositionError,
    build_reviewer_disposition_record,
    verify_records,
)
from okojo.narrator import narrate_chain
from okojo.narrator.narrator import (
    CASE_TEMPLATES,
    assert_calibrated,
    assert_narrative_grounded,
)


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-01-01T00:00:{n['i']:02d}+00:00"

    return clock


def _base_chain(tmp_path):
    """A minimal but realistic case chain ending in a ``packaged`` stamp."""
    log = AuditLog(tmp_path / "audit_log.jsonl", clock=_counter())
    log.append("orchestrator", "case_open", target="uid:500000003", detail="Jane Roe")
    log.append("case_packager", "packaged", target="case_package.json",
               detail='{"sha256":"abc123def456abc123def456abc123def456abc123def456abc1",'
                      '"disposition":"draft_sar"}')
    return log


_PACKAGE_SHA = "abc123def456abc123def456abc123def456abc123def456abc1"


def _build(records, disposition="Approve", rationale="Corroborated; cleared to file.",
           **over):
    kw = dict(
        subject_uid=500000003,
        package_sha256=_PACKAGE_SHA,
        disposition=disposition,
        rationale=rationale,
        reviewer="Reviewer A",
        timestamp="2026-01-01T00:05:00+00:00",
        packaged_seq=2,
    )
    kw.update(over)
    return build_reviewer_disposition_record(records, **kw)


# --------------------------------------------------------------------------- #
# (i) rationale required
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["", "   ", "\t\n  "])
def test_empty_rationale_cannot_produce_a_record(tmp_path, bad):
    records = _base_chain(tmp_path).read_all()
    with pytest.raises(DispositionError):
        _build(records, rationale=bad)


def test_unknown_disposition_rejected(tmp_path):
    records = _base_chain(tmp_path).read_all()
    with pytest.raises(DispositionError):
        _build(records, disposition="Reject")


def test_only_the_two_ruled_dispositions_are_accepted(tmp_path):
    records = _base_chain(tmp_path).read_all()
    for disp in ("Approve", "Review Needed"):
        rec = _build(records, disposition=disp)
        assert rec["actor"] == "human_reviewer"
        assert rec["action"] == "reviewer_disposition"


# --------------------------------------------------------------------------- #
# (ii) the session chain re-verifies after append
# --------------------------------------------------------------------------- #
def test_single_disposition_chains_and_reverifies(tmp_path):
    records = _base_chain(tmp_path).read_all()
    rec = _build(records)
    assert rec["seq"] == records[-1]["seq"] + 1
    assert rec["prev_hash"] == records[-1]["hash"]

    effective = records + [rec]
    ver = verify_records(effective)
    assert ver.ok and ver.verified_count == len(effective)

    # the payload carries every ruled field
    import json
    detail = json.loads(rec["detail"])
    assert detail == {
        "subject_uid": 500000003,
        "package_sha256": _PACKAGE_SHA,
        "disposition": "Approve",
        "rationale": "Corroborated; cleared to file.",
        "reviewer": "Reviewer A",
    }
    assert rec["target"] == "uid:500000003"
    assert rec["provenance"] == ["audit_chain[seq:2]"]  # cites the packaged record


def test_repeated_dispositions_keep_the_chain_intact(tmp_path):
    """Multiple sandbox decisions chain one onto the next; the chain stays valid."""
    records = _base_chain(tmp_path).read_all()
    effective = list(records)
    for i, disp in enumerate(("Review Needed", "Approve", "Review Needed")):
        rec = _build(effective, disposition=disp, rationale=f"pass {i}",
                     timestamp=f"2026-01-01T00:1{i}:00+00:00")
        effective.append(rec)
    ver = verify_records(effective)
    assert ver.ok and ver.verified_count == len(records) + 3
    assert [r["seq"] for r in effective] == list(range(1, len(records) + 4))


# --------------------------------------------------------------------------- #
# (iii) the canonical on-disk chain is byte-identical after sandbox dispositions
# --------------------------------------------------------------------------- #
def test_canonical_on_disk_bytes_are_untouched_by_sandbox_dispositions(tmp_path):
    log = _base_chain(tmp_path)
    path = log.path
    before = path.read_bytes()

    # Read the chain, append many dispositions purely (the sandbox path). The
    # builder writes NOTHING to disk, so the file cannot move.
    records = log.read_all()
    effective = list(records)
    for i in range(25):
        effective.append(_build(effective, disposition="Approve", rationale=f"r{i}",
                                timestamp=f"2026-01-01T01:{i:02d}:00+00:00"))
    assert len(effective) == len(records) + 25
    assert verify_records(effective).ok

    after = path.read_bytes()
    assert after == before, "sandbox dispositions must never write the canonical chain"


# --------------------------------------------------------------------------- #
# (iv) the narrator line for the new record type is grounded and calibrated
# --------------------------------------------------------------------------- #
def test_narrator_line_is_templated_grounded_and_calibrated(tmp_path):
    records = _base_chain(tmp_path).read_all()
    for disp in ("Approve", "Review Needed"):
        effective = records + [_build(records, disposition=disp)]
        nar = narrate_chain(effective, family="case", subject="uid:500000003")
        assert nar.verified
        last = nar.sentences[-1]
        # a specific template, not the generic fallback
        assert last.templated
        assert last.text.startswith("A human reviewer recorded ")
        assert disp in last.text
        assert "rationale recorded" in last.text
        assert last.ref.seq == effective[-1]["seq"]
        # grounding + calibration hold over the whole narrative (narrate_chain
        # already validates fail-closed; assert explicitly for the record)
        assert_narrative_grounded(nar, effective)
        assert_calibrated(nar)


def test_registry_has_the_forced_add_template():
    assert ("human_reviewer", "reviewer_disposition") in CASE_TEMPLATES


# --------------------------------------------------------------------------- #
# (v) falsification — break an invariant deliberately, then restore
# --------------------------------------------------------------------------- #
def test_falsification_tampered_disposition_breaks_verification(tmp_path):
    """Break invariant (ii): mutate the recorded rationale after the fact and the
    chain no longer verifies — the disposition is as tamper-evident as any other
    record. Restoring the byte returns the chain to green."""
    records = _base_chain(tmp_path).read_all()
    rec = _build(records, rationale="original rationale")
    effective = records + [rec]
    assert verify_records(effective).ok  # GREEN before tamper

    # RED — silently rewrite the rationale inside the recorded detail
    tampered = dict(rec, detail=rec["detail"].replace("original", "SILENTLY_EDITED"))
    broken = records + [tampered]
    ver = verify_records(broken)
    assert not ver.ok and ver.break_seq == tampered["seq"] and ver.reason == "hash_mismatch"

    # GREEN again — restore the original record
    assert verify_records(records + [rec]).ok


def test_falsification_ungrounded_disposition_line_is_rejected(tmp_path):
    """Break invariant (iv): a disposition sentence citing a record NOT in the
    chain is rejected by the grounding guard (fail-closed)."""
    from okojo.narrator.narrator import (
        AuditChainNarrative,
        NarrativeGroundingError,
        NarrativeSentence,
        RecordRef,
    )

    records = _base_chain(tmp_path).read_all()
    effective = records + [_build(records)]
    nar = narrate_chain(effective, family="case", subject="uid:500000003")
    bogus = NarrativeSentence(
        RecordRef(999999, "de" * 32), "action",
        "A human reviewer recorded Approve on the case package; rationale recorded.")
    injected = AuditChainNarrative(nar.family, nar.subject, nar.verified,
                                   nar.record_count, nar.sentences + [bogus])
    with pytest.raises(NarrativeGroundingError):
        assert_narrative_grounded(injected, effective)
