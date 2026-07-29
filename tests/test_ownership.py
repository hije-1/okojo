"""Beneficial-owner + officer walk unit tests (Phase 8 Part II T3a).

Exercises the pure ``walk_ownership`` directly (no ``run_sweep`` wiring — that is
T3b's eval). Every uid/id is derived structurally from the answer key, never
hardcoded. Ownership/officer edges are a DISTINCT edge type: the walk surfaces
control/status for review and can never fabricate flow exposure.
"""

from __future__ import annotations

from okojo.identity import OWNERSHIP_CONTROL_THRESHOLD, walk_ownership
from okojo.sar import GroundingResolver

_DES = "DES-2026-0005"          # the resolved true-hit party seeding the T3 walk
_DESIGNATION_DATE = "2026-01-30"


def _party_uid(ground_truth) -> int:
    return ground_truth["identity_variant_matches"][_DES][0]


def test_ownership_propagation_at_threshold_only(conn, ground_truth):
    """A company owned at/above the control threshold propagates; a below-
    threshold stake does not (the discrimination trap)."""
    res = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    got = sorted(p.company_uid for p in res.propagations)
    assert got == sorted(ground_truth["ownership_propagated_uids"])
    for p in res.propagations:
        assert p.ownership_pct >= OWNERSHIP_CONTROL_THRESHOLD
    # The below-threshold company the party also owns is NOT propagated.
    owned = {int(r["company_uid"]) for r in conn.beneficial_ownership()
             if int(r["owner_uid"]) == _party_uid(ground_truth)}
    assert len(owned) > len(got), "expected an owned company below the threshold"


def test_fictitious_executive_exact(conn, ground_truth):
    """Only the name-only officer with no resolvable footprint is flagged; the
    name-only officer whose name resolves to an account is NOT (discrimination)."""
    res = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    got = sorted(f.appointment_id for f in res.fictitious_executives)
    assert got == sorted(ground_truth["fictitious_executive_flags"])
    # There IS a name-only appointment that resolves (has footprint) — proving the
    # detector reads footprint, not the presence of officer_uid. An empty cell
    # round-trips as None/NaN via the connector clean step.
    def _name_only(r) -> bool:
        v = r["officer_uid"]
        return v is None or not str(v).strip() or str(v).lower() == "nan"
    name_only = [r for r in conn.officer_appointments() if _name_only(r)]
    assert len(name_only) > len(got), "expected a footprinted name-only officer too"


def test_post_designation_control_change_exact(conn, ground_truth):
    """Only the appointment dated after the designation is a control change; the
    pre-designation appointments are not."""
    res = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    got = sorted(c.appointment_id for c in res.control_changes)
    assert got == sorted(ground_truth["post_designation_control_changes"])
    for c in res.control_changes:
        assert c.changed_date > _DESIGNATION_DATE


def test_ownership_walk_adds_zero_exposure(conn, ground_truth):
    """DISTINCT-EDGE property: ownership/officer propagation never carries flow
    exposure (mirrors the gas-edge exclusion)."""
    res = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    assert not res.is_empty()
    assert res.exposure_usdt() == 0.0


def test_dismissed_or_absent_party_seeds_no_walk(conn):
    """No resolved party -> an empty walk (a corroboration dismissal seeds
    nothing)."""
    res = walk_ownership(conn, [], _DESIGNATION_DATE)
    assert res.is_empty()


def test_walk_findings_are_grounded(conn, ground_truth):
    """Every surfaced finding cites real evidence rows that resolve."""
    resolver = GroundingResolver(conn)
    res = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    for finding in (list(res.propagations) + list(res.fictitious_executives)
                    + list(res.control_changes)):
        assert finding.provenance
        assert all(resolver.resolves(p) for p in finding.provenance)


def test_walk_is_deterministic(conn, ground_truth):
    """Same inputs, byte-identical result (ordered, RNG-free)."""
    a = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    b = walk_ownership(conn, [_party_uid(ground_truth)], _DESIGNATION_DATE)
    assert a.model_dump() == b.model_dump()
