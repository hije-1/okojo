"""Phase 6: the decision-ready package is deterministic, audit-pinned, and
red-herring-safe.

Four guarantees:
  * structure — the package's top-level shape is pinned;
  * byte determinism — two clocked runs produce identical package files;
  * audit pinning — every referenced (seq, hash) resolves into the on-disk
    hash chain, the chain verifies, and the packaged stamp's sha256 matches
    the file on disk (the log covers the package; the package pins the log);
  * the internal-tag red herring is PRESERVED in the package as a flag with
    the never-obeyed policy line, while the disposition rationale derives
    from Critic coverage and never cites the tag.
"""

from __future__ import annotations

import hashlib
import json

from okojo.orchestrator import run_case
from okojo.packager import PACKAGE_VERSION

_TOP_KEYS = {
    "package_version", "readme", "subject", "red_herring", "recidivism",
    "disposition", "disposition_rationale", "decision_trace", "network",
    "risk_summary", "tells", "watchlist_alias_hits", "advisory",
    "rfi_followup", "sar_draft", "critic", "audit",
}


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-01-01T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}+00:00"

    return clock


def _package(res) -> dict:
    assert res.package_path is not None and res.package_path.exists()
    return json.loads(res.package_path.read_text(encoding="utf-8"))


def test_package_structure_pinned(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    pkg = _package(res)
    assert set(pkg.keys()) == _TOP_KEYS
    assert pkg["package_version"] == PACKAGE_VERSION
    assert pkg["disposition"] == "clears_bar"
    assert len(pkg["decision_trace"]) == len(res.decisions)
    assert pkg["advisory"]["primary"]["advisory_id"] == res.advisory.advisory_id
    assert (pkg["advisory"]["secondary_surfaced"]["advisory_id"]
            == res.secondary_advisory.advisory_id)
    assert pkg["rfi_followup"]["note"].startswith("discrete routine requests")
    assert pkg["sar_draft"]["claims"]
    assert pkg["critic"]["meets_bar"] is True
    assert pkg["recidivism"]["is_recidivist"] is False


def test_package_bytes_deterministic_under_injected_clock(conn, trust_uid, tmp_path):
    a = run_case(trust_uid, conn=conn, out_dir=tmp_path / "a",
                 render_graph=False, audit_clock=_counter())
    b = run_case(trust_uid, conn=conn, out_dir=tmp_path / "b",
                 render_graph=False, audit_clock=_counter())
    assert a.package_path.read_bytes() == b.package_path.read_bytes()
    assert a.package_sha256 == b.package_sha256


def test_package_is_pinned_to_the_audit_chain(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    pkg = _package(res)

    # every referenced (seq, actor, action, hash) resolves into the live chain
    by_seq = {r["seq"]: r for r in res.audit_records}
    for ref in pkg["audit"]["records"]:
        rec = by_seq[ref["seq"]]
        assert (rec["actor"], rec["action"], rec["hash"]) == (
            ref["actor"], ref["action"], ref["hash"])
    assert pkg["audit"]["verified"] is True
    assert res.audit_verified is True

    # the reference block was captured BEFORE the packaged stamp...
    tip_seq = pkg["audit"]["record_count"]
    assert pkg["audit"]["tip_hash"] == by_seq[tip_seq]["hash"]
    packaged = next(r for r in res.audit_records
                    if r["actor"] == "case_packager" and r["action"] == "packaged")
    assert packaged["seq"] > tip_seq

    # ...and the stamp then covers the package file (sha256 of the bytes)
    detail = json.loads(packaged["detail"])
    on_disk = hashlib.sha256(res.package_path.read_bytes()).hexdigest()
    assert detail["sha256"] == on_disk == res.package_sha256

    # the case graph recorded the same package hash
    from okojo.casegraph import CaseGraphStore
    store = CaseGraphStore(tmp_path / "case" / "case_graph.sqlite")
    dump = store.dump()
    assert dump["cases"][0][8] == res.package_sha256  # package_sha256 column


def test_red_herring_preserved_never_obeyed(conn, ground_truth, tmp_path):
    """The privileged 'do-not-block' tag reaches the reviewer as a FLAG with
    the policy line, and the disposition rationale cites the Critic's
    coverage, never the tag."""
    priv_uid = ground_truth["privileged_redherring_uid"]
    res = run_case(priv_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    pkg = _package(res)

    rh = pkg["red_herring"]
    assert rh is not None
    assert "internal" in rh["internal_tag"].lower()
    assert "never obeyed" in rh["policy"]
    assert rh["anomaly_code"] == "internal_account_tag"

    # disposition derives from the rubric, not the tag
    assert pkg["disposition"] == "human_review"
    rationale = pkg["disposition_rationale"].lower()
    assert "coverage" in rationale
    assert "internal" not in rationale and "tag" not in rationale
    # and no ring subject without a tag carries a red-herring block
    trust = run_case(ground_truth["network_member_uids"][3], conn=conn,
                     out_dir=tmp_path / "t", render_graph=False)
    assert _package(trust)["red_herring"] is None
