"""Proximity-ring unit tests (Phase 8 Part II T4a).

Exercises the pure ``build_proximity_ring`` directly (no ``run_sweep`` wiring —
that is T4b's eval). Every uid is derived structurally from the answer key. The
ring is REVIEW-tier: it surfaces candidate associates with their evidence, never
exposure and never asserted kinship, and is NEVER weighted by activity volume.
"""

from __future__ import annotations

from okojo.identity import build_proximity_ring
from okojo.sar import GroundingResolver

_DES = "DES-2026-0005"


def _party(ground_truth) -> int:
    return ground_truth["identity_variant_matches"][_DES][0]


def test_ring_matches_gold_exact(conn, ground_truth):
    ring = build_proximity_ring(conn, [_party(ground_truth)])
    assert ring.member_uids() == sorted(ground_truth["proximity_ring_uids"][_DES])


def test_dormant_included_active_stranger_excluded(conn, ground_truth):
    """The dormancy trap: a dormant (offboarded) relative surfaces, while an
    ACTIVE unrelated stranger does not — inclusion is independent of activity."""
    ring = build_proximity_ring(conn, [_party(ground_truth)])
    by_uid = {m.uid: m for m in ring.members}

    # A dormant member is present.
    dormant = [m for m in ring.members if m.account_status != "active"]
    assert dormant, "expected a dormant ring member (dormancy is not innocence)"

    # The active proximity persona with NO signals (the stranger) is out of the
    # ring even though it is active.
    proximity_accts = [a for a in conn.all_accounts()
                       if str(a["role_in_ring"]) == "proximity_review_subject"]
    stranger = [a for a in proximity_accts
                if int(a["uid"]) not in by_uid and str(a["account_status"]) == "active"]
    assert stranger, "expected an active stranger persona excluded from the ring"


def test_signals_are_grounded(conn, ground_truth):
    """Every ring member cites real evidence rows for the signals that surfaced
    it (and any weighting evidence)."""
    resolver = GroundingResolver(conn)
    ring = build_proximity_ring(conn, [_party(ground_truth)])
    for m in ring.members:
        assert m.primary_signals, m.uid
        for p in m.provenance:
            assert resolver.resolves(p), (m.uid, p.cite())


def test_kinship_never_asserted_as_fact(conn, ground_truth):
    """Calibrated language: ring notes surface a CORRELATIONAL signal, never an
    assertion of kinship (no 'is the sister/brother of ...')."""
    ring = build_proximity_ring(conn, [_party(ground_truth)])
    for m in ring.members:
        low = m.note.lower()
        assert "candidate" in low or "possible" in low
        assert "correlational" in low
        for banned in ("is the sister", "is the brother", "is the spouse",
                       "is the parent", "is related to"):
            assert banned not in low, (m.uid, banned)


def test_ring_adds_zero_exposure(conn, ground_truth):
    """REVIEW-tier, never exposure: the ring carries no flow exposure."""
    ring = build_proximity_ring(conn, [_party(ground_truth)])
    assert not ring.is_empty()
    assert ring.exposure_usdt() == 0.0


def test_excluded_accounts_never_in_ring(conn, ground_truth):
    """Accounts already surfaced elsewhere (exposed/adjacent) are excluded — the
    ring is the otherwise-unconnected associates."""
    party = _party(ground_truth)
    full = set(build_proximity_ring(conn, [party]).member_uids())
    victim = min(full)
    trimmed = set(build_proximity_ring(conn, [party], exclude_uids={victim}).member_uids())
    assert victim not in trimmed
    assert trimmed == full - {victim}


def test_no_party_no_ring(conn):
    assert build_proximity_ring(conn, []).is_empty()


def test_deterministic(conn, ground_truth):
    a = build_proximity_ring(conn, [_party(ground_truth)])
    b = build_proximity_ring(conn, [_party(ground_truth)])
    assert a.model_dump() == b.model_dump()
