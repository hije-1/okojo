"""Identity Resolution (Phase 8 Part II).

Given a designated name (foreign or domestic), resolve which customers might BE
that party — across romanization variants, with corroboration before any
assertion. Everything here is REVIEW-tier proposal: the layer *surfaces* and
*proposes*; a human resolves. The agent never asserts identity as fact.

This package owns its OWN versioned policy (``identity_config`` /
``IDENTITY_VERSION``) — the ninth doc<->code anti-drift pair — declared COMPLETE
here in T1 (transliteration tables + the variant threshold now; the ownership-
propagation threshold and proximity-signal registry are reserved and consumed
by T3/T4 with no further version bump, mirroring how ``sweep_config`` declared
its full Part-I-B surface in Slice S1).

PRODUCTION POSTURE (vendor-agnostic): the variant-matching layer below is the
piece an institution would, in a real deployment, delegate to a commercial
screening API. Okojo's distinct value is what no screening vendor provides —
registry governance (visible absence), corroboration-before-proposal, calibrated
action proposals, and the tamper-evident audit chain. No vendor is named or
implied; this is an in-house reference implementation over synthetic data.
"""

from __future__ import annotations

IDENTITY_VERSION = "1.0.0"

# Fuzzy match threshold (RapidFuzz WRatio, 0-100) for scoring a customer name
# against an EXPANDED designated-name variant. Declared as its own pinned policy
# parameter — a tripwire test asserts it equals the sweep's NAME_MATCH_THRESHOLD
# (and, transitively, the SDN screener's SCREEN_THRESHOLD), so the variant layer
# can never silently run at a different bar than the direct screen it sharpens.
# Intentional divergence must be argued through an IDENTITY_VERSION bump.
VARIANT_MATCH_THRESHOLD = 85

# --- RESERVED for later Part-II slices (declared complete here, consumed with
# no further version bump) -------------------------------------------------- #
# T3 (beneficial-owner + officer walk): the documented ownership fraction at or
# above which designation status propagates through an ownership edge. A tunable
# POLICY parameter stated at principle level (majority-ownership control), never
# a statute citation. Ownership/officer edges are a DISTINCT edge type that can
# never fabricate flow exposure (the gas-edge discipline).
OWNERSHIP_CONTROL_THRESHOLD = 0.50

# T4 (proximity ring): the correlational signals by which a relative/associate
# of a resolved designated party is SURFACED for review (never exposure, never
# asserted kinship, never weighted by activity volume). Reserved registry; the
# detectors land in T4.
PROXIMITY_SIGNAL_REGISTRY = [
    {"id": "shared_surname", "description": "shared surname / patronymic token"},
    {"id": "shared_kyc_attribute", "description": "shared KYC attribute (address, contact)"},
    {"id": "declared_relationship", "description": "declared-relationship metadata on file"},
    {"id": "relationship_remark", "description": "a relationship-asserting free-text remark"},
    {"id": "shared_device", "description": "a shared device_fingerprint"},
    {"id": "email_handle_pattern", "description": "a shared email-handle pattern"},
    {"id": "kyc_document_cross_holding", "description": "KYC documents of one party inside another's account"},
]

# --------------------------------------------------------------------------- #
# Transliteration equivalence rule tables — CYRILLIC and ARABIC romanization
# families, built ONLY from PUBLISHED romanization conventions (cited per
# family). These are bounded, illustrative equivalence classes, NOT a complete
# transliteration engine: they encode the specific published divergences a
# name-screen must bridge (a customer opening an account under a different
# published romanization of a designated name slides past an exact-match, and
# often past a single-script fuzzy, screen). Each class names the underlying
# name-part and the standards whose romanizations it unifies. No proprietary or
# scraped table is used; every form is a documented public romanization.
# --------------------------------------------------------------------------- #
TRANSLITERATION_FAMILIES = {
    "cyrillic": {
        "romanization_standards": [
            "BGN/PCGN 1947 (Romanization of Russian)",
            "ISO 9:1995 (Transliteration of Cyrillic)",
            "ALA-LC Romanization Tables (Russian)",
            "UNGEGN / GOST 7.79 System B",
        ],
        "equivalence_classes": [
            {
                "id": "cyr-yevgeniy",
                "forms": ["yevgeniy", "evgenii", "evgeny", "yevgeni"],
                "basis": "Cyrillic Е initial (Ye- BGN/PCGN vs E- ISO 9) and "
                         "-ий ending (-iy / -ii / -y across standards)",
            },
            {
                "id": "cyr-skiy",
                "forms": ["zhukovskiy", "zhukovsky", "zhukovski"],
                "basis": "-ский surname ending romanized -skiy (BGN/PCGN) / "
                         "-sky (traditional) / -ski (ISO 9)",
            },
            {
                "id": "cyr-aleksandr",
                "forms": ["aleksandr", "alexander", "aleksander"],
                "basis": "Александр — Cyrillic кс as ks (ISO 9 / ALA-LC) vs x "
                         "(traditional English)",
            },
            {
                "id": "cyr-ov",
                "forms": ["volkov", "volkoff"],
                "basis": "-ов surname ending: -ov (modern standards) vs -off "
                         "(older French/passport transliteration)",
            },
        ],
    },
    "arabic": {
        "romanization_standards": [
            "BGN/PCGN 1956 (Romanization of Arabic)",
            "ISO 233:1984 (Transliteration of Arabic)",
            "ALA-LC Romanization Tables (Arabic)",
            "UNGEGN (Arabic)",
        ],
        "equivalence_classes": [
            {
                "id": "ara-muhammad",
                "forms": ["muhammad", "mohammed", "mohamed", "mohamad", "muhammed"],
                "basis": "محمد — short-vowel a/o and gemination differences "
                         "across BGN/PCGN, ISO 233, and common usage",
            },
            {
                "id": "ara-article",
                "forms": ["al", "el", "ul"],
                "basis": "the definite article ال romanized al- (BGN/PCGN, "
                         "ISO 233) vs el- / ul- (regional/common usage)",
            },
            {
                "id": "ara-sayigh",
                "forms": ["sayigh", "sayegh", "sayagh"],
                "basis": "long-vowel and غ (gh) rendering differences in the "
                         "surname الصايغ across standards",
            },
            {
                "id": "ara-rashid",
                "forms": ["rashid", "rasheed", "rachid"],
                "basis": "long ī romanized -i (ISO 233) vs -ee (common) and "
                         "ش as sh vs ch (Francophone)",
            },
        ],
    },
}


def _equivalence_classes() -> list[dict]:
    """A flat, ordered list of every equivalence class with its family — the
    expansion engine's rule set. Ordered by family then declaration order, so
    variant enumeration is deterministic (no set iteration)."""
    flat: list[dict] = []
    for family in ("cyrillic", "arabic"):
        for cls in TRANSLITERATION_FAMILIES[family]["equivalence_classes"]:
            flat.append({"id": cls["id"], "family": family, "forms": list(cls["forms"])})
    return flat


def identity_config() -> dict:
    """The full, versioned identity-resolution policy — the ninth anti-drift pair.

    Single source of truth: stamped into the sweep's audit chain once per run
    (``remediation_sweep / identity_config``) and regression-tested against
    ``docs/identity-methodology.md`` so code and published methodology can never
    silently drift. The full Part-II surface is declared COMPLETE here in T1 —
    the transliteration tables and variant threshold are consumed now; the
    ownership-propagation threshold and proximity-signal registry are reserved
    and consumed by T3/T4 with no further version bump.
    """
    return {
        "version": IDENTITY_VERSION,
        "variant_match_threshold": VARIANT_MATCH_THRESHOLD,
        "transliteration_families": {
            family: {
                "romanization_standards": list(spec["romanization_standards"]),
                "equivalence_classes": [
                    {"id": c["id"], "forms": list(c["forms"]), "basis": c["basis"]}
                    for c in spec["equivalence_classes"]
                ],
            }
            for family, spec in TRANSLITERATION_FAMILIES.items()
        },
        "ownership_control_threshold": OWNERSHIP_CONTROL_THRESHOLD,
        "proximity_signal_registry": [dict(s) for s in PROXIMITY_SIGNAL_REGISTRY],
        "posture": (
            "REVIEW-tier throughout: the layer surfaces and proposes; a human "
            "resolves. Identity and kinship are never asserted as fact. The "
            "variant-matching layer is what a real deployment would delegate to "
            "a commercial screening API; Okojo's distinct value is registry "
            "governance, corroboration-before-proposal, calibrated proposals, "
            "and the tamper-evident chain (no vendor named or implied)."
        ),
    }


from .variants import (  # noqa: E402
    VariantNameMatch,
    expand_name_variants,
    screen_name_variants,
)
from .ownership import (  # noqa: E402
    ControlChangeFlag,
    FictitiousExecutiveFlag,
    OwnershipPropagation,
    OwnershipWalkResult,
    walk_ownership,
)
from .proximity import (  # noqa: E402
    ProximityRing,
    ProximityRingMember,
    ProximitySignal,
    build_proximity_ring,
)

__all__ = [
    "IDENTITY_VERSION",
    "VARIANT_MATCH_THRESHOLD",
    "OWNERSHIP_CONTROL_THRESHOLD",
    "PROXIMITY_SIGNAL_REGISTRY",
    "TRANSLITERATION_FAMILIES",
    "identity_config",
    "VariantNameMatch",
    "expand_name_variants",
    "screen_name_variants",
    "OwnershipWalkResult",
    "OwnershipPropagation",
    "FictitiousExecutiveFlag",
    "ControlChangeFlag",
    "walk_ownership",
    "ProximityRing",
    "ProximityRingMember",
    "ProximitySignal",
    "build_proximity_ring",
]
