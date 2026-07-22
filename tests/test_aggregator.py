"""Profile Aggregator surfaces the right grounded anomalies."""

from __future__ import annotations

from okojo.aggregator import build_profile
from okojo.aggregator.anomalies import detect_reused_kyc


def test_trust_profile_flags_sanctioned_ip_and_shared_device(conn, trust_uid):
    profile = build_profile(conn, trust_uid)
    codes = profile.anomaly_codes()
    assert "sanctioned_jurisdiction_ip" in codes
    assert "shared_device_fingerprint" in codes
    # every anomaly is grounded
    for a in profile.anomalies:
        assert a.provenance, f"anomaly {a.code} has no provenance"


def test_timeline_is_chronological_and_grounded(conn, trust_uid):
    profile = build_profile(conn, trust_uid)
    ts = [e.timestamp for e in profile.events]
    assert ts == sorted(ts)
    assert profile.events, "expected at least one timeline event"
    for e in profile.events:
        assert e.provenance


def test_reused_kyc_detector_fires_on_a_reused_group(conn, ground_truth):
    # Pick an account that ground truth says shares its KYC doc, and confirm the
    # detector fires when that account is the subject.
    doc_id, uids = next(iter(ground_truth["reused_kyc_docs"].items()))
    subject = conn.get_account(uids[0])
    anomalies = detect_reused_kyc(conn, subject)
    assert any(a.code == "reused_kyc_document" for a in anomalies)


def test_internal_tag_is_flagged_not_obeyed(conn, ground_truth):
    priv_uid = ground_truth["privileged_redherring_uid"]
    profile = build_profile(conn, priv_uid)
    assert "internal_account_tag" in profile.anomaly_codes()
