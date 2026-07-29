"""Geo-triangulation scorecard — the TERRITORY sweep (Phase 8 Part III U1b).

Calibrated framing (P8-B): the P/R/F1 below is an EXACT-SET consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the discrimination — the one-signal rule surfaces exactly the
personas with a positive location signal and NO others; the carrier-only hit
fires on a region-exclusive carrier with an inconclusive prefix; the VPN-slip
hit is the ambiguous traveller (a territory IP in a gap of otherwise-continuous
VPN use); the decoy (a prefix look-alike not in the registry) must NOT fire.
The answer key is DEFINITIONAL (which persona carries which data, by
construction); ``run_geo_triangulation`` recomputes the surfaced set from the
signals, so the check is real, never circular.
"""

from __future__ import annotations

import json

from okojo.eval.metrics import score
from okojo.geo import geo_config
from okojo.sweep import designation_from_record, run_sweep


def _territory_designation(conn):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    tid = next(i for i in recs if str(recs[i]["list_type"]) == "territory")
    return designation_from_record(recs[tid])


def test_geo_surfaced_scorecard(conn, ground_truth, tmp_path, capsys):
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)

    predicted = {dd.uid for dd in res.geo_dossiers}
    gold = set(ground_truth["geo_surfaced_uids"])
    sc = score(predicted, gold)

    lines = []
    for dd in res.geo_dossiers:
        # The one-signal rule: every surfaced account carries >=1 positive signal.
        assert dd.surfaced and dd.signals
        # Grounding: every surfaced line (signal / counter-evidence / gap /
        # marker) cites a real evidence row.
        for p in dd.provenance:
            assert p.source and p.row_key
        # Calibrated language throughout — indicates possible presence, never
        # "proves"; VPN is never asserted as location.
        low = dd.note.lower() + " " + " ".join(s.detail.lower() for s in dd.signals)
        assert "prove location" not in low and "proves location" not in low
        assert "possible presence" in low
        lines.append(f"  uid={dd.uid} {dd.entity_name}: {dd.signal_ids()}")

    with capsys.disabled():
        print("\nPhase 8 geo-triangulation scorecard (TERRITORY sweep -- exact-set):")
        for ln in lines:
            print(ln)
        print(f"  geo_surfaced: {sc}")
        print(f"  gold: {sorted(gold)}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    assert predicted == gold
    assert res.audit_verified


def test_geo_discrimination_subcases(conn, ground_truth, tmp_path):
    """The carrier-only, VPN-slip, counter-evidence, and decoy cases each behave
    exactly as constructed — the evidentiary weight behind the scorecard."""
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)
    by_uid = {dd.uid: dd for dd in res.geo_dossiers}

    # Carrier-only: surfaced by the region-exclusive carrier alone (prefix
    # inconclusive), so the ONLY signal is exclusive_carrier.
    (carrier_uid,) = ground_truth["geo_carrier_only_uids"]
    assert by_uid[carrier_uid].signal_ids() == ["exclusive_carrier"]

    # VPN-slip: the ambiguous traveller — surfaced on the slip alone, with an
    # EXPIRED foreign residency card (degraded counter-evidence) and a KYC-refresh
    # control gap (the dual flag).
    (slip_uid,) = ground_truth["geo_vpn_slip_uids"]
    trav = by_uid[slip_uid]
    assert trav.signal_ids() == ["vpn_slip"] and trav.has_vpn_slip()
    assert trav.vpn_markers, "the traveller's VPN use is recorded as markers"
    (ce_uid,) = ground_truth["geo_counter_evidence_uids"]
    assert ce_uid == slip_uid
    assert trav.counter_evidence and trav.counter_evidence[0].counterweight == "degraded"
    assert [g.gap_type for g in trav.control_gaps] == ["kyc_refresh_expired"]

    # Decoy: a prefix look-alike not in the territory registry — never surfaced.
    (decoy_uid,) = ground_truth["geo_decoy_absent_uids"]
    assert decoy_uid not in by_uid


def test_geo_config_and_stamp_in_territory_chain(conn, tmp_path):
    """The geo policy is stamped into the territory sweep's chain exactly once
    (the U1b companion to the methodology doc-drift test), the geo_triangulation
    record lands once, and the chain verifies. A DOMESTIC sweep carries NEITHER
    stamp (the stage is conditional on the territory kind)."""
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)

    cfg = [r for r in res.audit_records
           if r["actor"] == "remediation_sweep" and r["action"] == "geo_config"]
    assert len(cfg) == 1, "geo_config stamped exactly once per territory run"
    assert json.loads(cfg[0]["detail"]) == geo_config()
    tri = [r for r in res.audit_records
           if r["actor"] == "remediation_sweep" and r["action"] == "geo_triangulation"]
    assert len(tri) == 1
    surfaced_ids = {x["uid"] for x in json.loads(tri[0]["detail"])["surfaced"]}
    assert surfaced_ids == {dd.uid for dd in res.geo_dossiers}
    assert res.audit_verified

    # A non-territory (domestic) designation carries no geo_triangulation record.
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    dom_id = next(i for i in recs if str(recs[i]["list_type"]) == "sdn_style"
                  and str(recs[i]["designated_addresses"]))
    dom = run_sweep(designation_from_record(recs[dom_id]), out_dir=tmp_path / "dom", conn=conn)
    assert not [r for r in dom.audit_records
                if r["action"] in ("geo_triangulation", "geo_config")]
    assert dom.geo_dossiers == []
