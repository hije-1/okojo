"""Phase 8 Part III: the geo-triangulation policy is explainable AND reproducible.

The tenth doc<->code anti-drift pair. The published methodology doc's canonical
policy block equals ``geo_config()`` exactly. (The companion "config is stamped
into the sweep's audit chain" assertion lands with the U1b wiring, once a
territory designation exists to sweep — see ``test_geo_eval.py``.)
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.geo import GEO_VERSION, geo_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "geo-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- geo-config:begin -->")
    hi = text.index("<!-- geo-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals geo_config() exactly."""
    assert _doc_config() == geo_config()


def test_methodology_doc_states_current_version():
    assert f"v{GEO_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_methodology_doc_states_posture_and_synthetic():
    """Calibrated REVIEW-tier posture, the one-signal rule, the VPN discipline,
    and the synthetic/advisory-inert stance are all stated positively."""
    text = _DOC.read_text(encoding="utf-8").lower()
    assert "review-tier" in text
    assert "indicates possible presence" in text or "indicate possible presence" in text
    assert "never" in text and "location evidence" in text        # VPN discipline
    assert "one-signal rule" in text
    assert "named by no advisory" in text                          # advisory inertness
    assert "synthetic" in text and "fictional" in text


def test_config_declares_all_six_collectors_plus_slip():
    """The registry declares the six collectors + the VPN-slip form, complete."""
    ids = {s["id"] for s in geo_config()["signal_registry"]}
    assert ids == {
        "ip_geolocation", "phone_prefix", "exclusive_carrier", "kyc_geography",
        "declared_residence", "device_timezone", "vpn_slip",
    }


def test_config_declares_proposal_menu_complete():
    """The proposal menu is declared complete here (consumed by U2)."""
    ids = [p["id"] for p in geo_config()["proposal_menu"]]
    assert ids == [
        "propose_edd_rfi", "propose_withdrawal_only_restriction",
        "propose_trade_and_withdrawal_block", "propose_full_block_and_escalate",
    ]
