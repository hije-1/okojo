"""Geo Triangulation (Phase 8 Part III).

A new designation KIND — **TERRITORY** — designates a *geography*, not a party.
The sweep response differs in kind: **no name screen**; instead collect location
signals per account and **triangulate** possible presence inside the sanctioned
region, signal by signal (the practitioner's manual geo-sweep). Everything is
REVIEW-tier and calibrated: a signal **indicates possible presence**, never
**proves location**; a human resolves.

This package owns its OWN versioned policy — ``geo_config`` / ``GEO_VERSION`` —
the **tenth** doc<->code anti-drift pair, declared COMPLETE here in U1a (all six
signal collectors, the one-signal rule, the VPN discipline incl. the slip rule,
the staleness modifier, and the proposal menu are all declared now; U1b consumes
the collectors and U2 consumes the proposal menu with NO further version bump —
the same discipline ``identity_config`` used in T1 and ``sweep_config`` in S1).

All data is SYNTHETIC: the territory is a fictional region (no real
occupied-territory name), the carriers are invented (no real carrier), and the
territory / country codes are named by no advisory (advisory-ranking inertness).
"""

from __future__ import annotations

GEO_VERSION = "1.0.0"

from .signals import (  # noqa: E402
    COUNTER_EVIDENCE_DOC_TYPES,
    WEIGHT_HIGH_VALUE,
    WEIGHT_STANDARD,
    WEIGHT_WEAK,
    GeoControlGap,
    GeoCounterEvidence,
    GeoDossier,
    GeoSignal,
    GeoVpnMarker,
    TerritoryProfile,
    assemble_dossier,
    collect_counter_evidence,
    collect_declared_residence,
    collect_device_timezone,
    collect_exclusive_carrier,
    collect_ip_geolocation,
    collect_kyc_geography,
    collect_phone_prefix,
    collect_vpn_markers,
    collect_vpn_slip,
)

# The six signal collectors + the VPN-slip form — the published signal registry.
# ``weight_class`` is a tunable, published attribute (a region-locked carrier or a
# VPN-slip is a stronger locator than a shared timezone); it is recorded on every
# signal now and consumed by the (U2) proposal rule with no version bump.
SIGNAL_REGISTRY = [
    {"id": "ip_geolocation", "source": "ip_logs", "weight_class": WEIGHT_STANDARD,
     "description": "a non-VPN login IP resolving into the territory"},
    {"id": "phone_prefix", "source": "phone_registrations", "weight_class": WEIGHT_STANDARD,
     "description": "a regional dialling prefix on the registered number"},
    {"id": "exclusive_carrier", "source": "phone_registrations + exclusive_carriers",
     "weight_class": WEIGHT_HIGH_VALUE,
     "description": "a carrier that operates ONLY inside the territory (a signal "
                    "even when the prefix is inconclusive)"},
    {"id": "kyc_geography", "source": "kyc_docs", "weight_class": WEIGHT_STANDARD,
     "description": "a KYC identity document issued within the territory"},
    {"id": "declared_residence", "source": "accounts", "weight_class": WEIGHT_STANDARD,
     "description": "the account's declared residence jurisdiction is the territory"},
    {"id": "device_timezone", "source": "device_timezones", "weight_class": WEIGHT_WEAK,
     "description": "a device clock set to the territory's timezone (coarse)"},
    {"id": "vpn_slip", "source": "ip_logs", "weight_class": WEIGHT_HIGH_VALUE,
     "description": "a territory IP observed in a gap of otherwise-continuous VPN "
                    "use (higher-value than an ordinary IP hit)"},
]

# The one-signal rule (verbatim practitioner testimony): any single positive
# location signal surfaces the account for review; signals then accumulate.
ONE_SIGNAL_RULE = (
    "ANY single positive location signal surfaces the account for review. Signals "
    "then accumulate into the totality dossier — more signals strengthen the "
    "picture, but one is sufficient to surface. Calibrated throughout: signals "
    "indicate possible presence, never prove location."
)

# VPN discipline: never location evidence; the slip is the one higher-value form.
VPN_DISCIPLINE = {
    "rule": "VPN use is NEVER location evidence; it is recorded in the dossier as "
            "an obfuscation/contradiction marker.",
    "vpn_slip": "a territory IP observed during a gap in otherwise-continuous VPN "
                "use is a HIGHER-VALUE signal than an ordinary IP hit; the dossier "
                "cites the slip window (the bracketing VPN timestamps) explicitly.",
}

# Document-staleness modifier — NOT a location signal. Counter-evidence (a
# residency document issued outside the territory) argues against presence; an
# EXPIRED one argues much less. The modifier is CATEGORICAL here (the numeric use,
# if any, belongs to the U2 proposal rule and the Q6 threshold mapping).
STALENESS_MODIFIER = {
    "gap_categories": ["MISSING", "EXPIRED"],
    "counter_evidence_doc_types": list(COUNTER_EVIDENCE_DOC_TYPES),
    "counterweight_by_status": {"valid": "full", "expired": "degraded", "missing": "none"},
    "rule": "a residency/domicile document issued OUTSIDE the territory argues "
            "against presence; if EXPIRED its counter-weight is degraded, if "
            "MISSING it carries none. Document staleness is NEVER read as evidence "
            "of presence.",
    "dual_flag": "an EXPIRED or MISSING counter-document also raises a KYC-refresh "
                 "control gap — the exchange failed to re-verify — surfaced for "
                 "the control owner, separately from any location signal.",
}

# The proposal menu (declared complete; the mapping rule + thresholds are U2, and
# come to the PM before U2a builds). PROPOSAL ONLY — no action is executed.
PROPOSAL_MENU = [
    {"id": "propose_edd_rfi",
     "description": "ask the customer (an enhanced-due-diligence identity/geography "
                    "RFI) — the honest proposal when the totality cannot resolve"},
    {"id": "propose_withdrawal_only_restriction",
     "description": "propose a withdrawal-only restriction for human action"},
    {"id": "propose_trade_and_withdrawal_block",
     "description": "propose a trade + withdrawal block for human action"},
    {"id": "propose_full_block_and_escalate",
     "description": "propose a full block and escalation for human action"},
]


def geo_config() -> dict:
    """The full, versioned geo-triangulation policy — the tenth anti-drift pair.

    Single source of truth: stamped into the sweep's audit chain once per
    territory run (``remediation_sweep / geo_config``) and regression-tested
    against ``docs/geo-methodology.md`` so code and published methodology can
    never silently drift. Declared COMPLETE in U1a — the collectors are consumed
    in U1b and the proposal menu in U2, with no further version bump."""
    return {
        "version": GEO_VERSION,
        "signal_registry": [dict(s) for s in SIGNAL_REGISTRY],
        "one_signal_rule": ONE_SIGNAL_RULE,
        "vpn_discipline": dict(VPN_DISCIPLINE),
        "staleness_modifier": {
            "gap_categories": list(STALENESS_MODIFIER["gap_categories"]),
            "counter_evidence_doc_types": list(STALENESS_MODIFIER["counter_evidence_doc_types"]),
            "counterweight_by_status": dict(STALENESS_MODIFIER["counterweight_by_status"]),
            "rule": STALENESS_MODIFIER["rule"],
            "dual_flag": STALENESS_MODIFIER["dual_flag"],
        },
        "proposal_menu": [dict(p) for p in PROPOSAL_MENU],
        "posture": (
            "REVIEW-tier throughout: the layer surfaces and (in U2) proposes; a "
            "human resolves. Presence is never asserted as fact. A TERRITORY "
            "designation has no name screen — location signals are triangulated "
            "instead. All data is synthetic: a fictional region, invented "
            "carriers, and territory/country codes named by no advisory."
        ),
    }


__all__ = [
    "GEO_VERSION",
    "SIGNAL_REGISTRY",
    "ONE_SIGNAL_RULE",
    "VPN_DISCIPLINE",
    "STALENESS_MODIFIER",
    "PROPOSAL_MENU",
    "COUNTER_EVIDENCE_DOC_TYPES",
    "WEIGHT_STANDARD",
    "WEIGHT_HIGH_VALUE",
    "WEIGHT_WEAK",
    "geo_config",
    "TerritoryProfile",
    "GeoSignal",
    "GeoVpnMarker",
    "GeoCounterEvidence",
    "GeoControlGap",
    "GeoDossier",
    "assemble_dossier",
    "collect_ip_geolocation",
    "collect_phone_prefix",
    "collect_exclusive_carrier",
    "collect_kyc_geography",
    "collect_declared_residence",
    "collect_device_timezone",
    "collect_vpn_markers",
    "collect_vpn_slip",
    "collect_counter_evidence",
]
