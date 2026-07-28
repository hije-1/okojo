"""Designation-Triggered Remediation Sweep (Phase 8, component 9).

A SECOND orchestration entry point over the finished core: input a synthetic
OFAC-style designation (name + on-chain addresses) and sweep the full ledger
for exposed accounts, verify hold status across the two sanctions-hold mock
systems, and surface the results for human remediation.

Deliberately a plain sequential pipeline, not a second LangGraph: agentic
machinery belongs only where genuine decisions exist, and the sweep has none
that branch — every stage runs, in order, every time. The sweep REUSES the
core (connectors, provenance, audit log, grounding) and never modifies it:
``run_sweep`` writes its own fresh audit chain under ``data/sweeps/`` and
never touches ``data/cases/`` or any case chain.
"""

from __future__ import annotations

SWEEP_VERSION = "1.1.0"

# Fuzzy name-match threshold (RapidFuzz WRatio, 0-100) for screening account
# names against the designated name. Mirrors the SDN screener's
# SCREEN_THRESHOLD — the same separation argument applies (transliteration
# variants score ~90+, unrelated names sit well below) — but is pinned here as
# its own versioned policy parameter so a screener retune can never silently
# move sweep behaviour without a SWEEP_VERSION bump. A test asserts the two
# agree, so intentional divergence must be argued, not accidental.
NAME_MATCH_THRESHOLD = 85

# Exposure is DIRECT when hops <= 1: the account controls a designated address
# (hops 0) or a single transaction of its lands on one (hops 1).
DIRECT_HOP_MAX = 1

# Remediation action vocabulary, most severe first. Calibrated: the sweep
# *proposes* and *flags* — it never blocks, unblocks, or mutates any status.
# The severity rank is a row's position here (the triage sort's first key).
#
# Declared COMPLETE for Part I-B in Slice S1 (the version bumps once, 1.1.0),
# mirroring how Slice B declared the triage fields ahead of Slice C: the three
# reserved entries are consumed later — foreign-signal and name-match rows in
# S2, the severe insider flag in S3 — and are inserted here now in their final
# severity slots so no later slice reorders the vocabulary (which would be a
# config change, i.e. a version bump). The five Part-I actions keep their
# original RELATIVE order, so a domestic worksheet's triage is byte-unchanged.
ACTION_VOCABULARY = [
    "proposes_designation_hold_review",       # exposed, no hold yet — act
    "flags_reconciliation_gap",               # exposed, hold-state drift — true up first
    "flags_insider_staff_device_overlap",     # S3: staff device overlap with the ring (severe)
    "proposes_confirm_existing_hold",         # exposed, already blocked — confirm
    "flags_foreign_signal_exposure_for_review",  # S2: foreign-list flow exposure (signal, review)
    "flags_name_match_for_identity_review",   # S2: name-only foreign-list match (review)
    "flags_internal_tag_for_review",          # adjacency + internal tag (flagged, never obeyed)
    "flags_for_review_non_flow_linkage",      # generic non-flow linkage
]

# Part I-B: the published list-source registry — which lists the sweep screens
# against, and with what standing. Each regime carries an EXPLICIT ``ingested``
# flag (per the visible-absence principle): a declared-but-not-ingested regime
# is a DOCUMENTED absence stamped into every run, never a silent gap inferred
# from an empty result. ``obligation_vs_signal`` here is the regime's DEFAULT
# standing; a foreign national-CT listing is a risk signal with a timestamp,
# never an obligation binding this synthetic exchange.
LIST_SOURCE_REGISTRY = {
    "SYN-DOMESTIC-OFAC": {
        "name": "Synthetic Domestic Sanctions List (OFAC-style)",
        "list_type": "sdn_style",
        "default_obligation_vs_signal": "obligation",
        "ingested": True,
        "ingestion_provenance_note": (
            "primary domestic designation feed; entries carry on-chain "
            "identifiers and bind the exchange (obligation)"
        ),
    },
    "SYN-FOREIGN-NCT": {
        "name": "Synthetic Foreign National Counter-Terrorism List",
        "list_type": "national_ct",
        "default_obligation_vs_signal": "signal",
        "ingested": True,
        "ingestion_provenance_note": (
            "foreign national counter-terrorism list; ingested as a "
            "timestamped RISK SIGNAL for cross-list early warning, never as a "
            "legal obligation of this synthetic exchange"
        ),
    },
    "SYN-UN-CONSOLIDATED": {
        "name": "Synthetic UN-style Consolidated List",
        "list_type": "un_style",
        "default_obligation_vs_signal": "obligation",
        "ingested": False,
        "ingestion_provenance_note": (
            "declared and NOT ingested in this prototype — published here and "
            "stamped into every sweep so its absence is a documented fact, not "
            "a silent configuration decision (visible absence)"
        ),
    },
}

# Part I-B: the published KYC required-artifact standard, per account entity
# type — the yardstick S3's KYC-completeness check measures each in-scope
# account against. Declared here (visible-absence applied to onboarding
# artifacts): the standard is versioned and stamped, so what counts as a KYC
# gap on a given date is a published policy, never an implicit one.
REQUIRED_ARTIFACTS = {
    "individual": ["government_id", "proof_of_address"],
    "company": ["certificate_of_incorporation", "beneficial_ownership"],
}

# Deterministic triage sort for the worksheet (Slice C): severity rank of the
# recommended action, then largest exposure, then closest hop, then uid.
TRIAGE_ORDER = ["action_severity", "-exposure_usdt", "hops", "uid"]

# Reconciliation taxonomy: (warehouse_status, admin_status) -> gap_type. The
# admin system is the operational system of record; the warehouse is the
# analytics feed copy. The two defensive "missing_*" types cover one-sided
# rows, which the synthetic tables never contain (full coverage is asserted).
GAP_TAXONOMY = {
    "missed_sync_block": "admin blocked, warehouse no_hold (feed never synced the block)",
    "unrecorded_unblock": "warehouse blocked, admin no_hold (release never synced back)",
    "missing_in_warehouse": "account absent from the warehouse feed copy",
    "missing_in_admin": "account absent from the admin system of record",
}


def sweep_config() -> dict:
    """The full, versioned sweep policy — every tunable behind the sweep.

    Single source of truth: stamped into the sweep's audit chain once per run
    (``remediation_sweep / sweep_config``) and regression-tested against the
    published methodology doc so the two can never silently drift. The full
    Part I-B surface — the list-source registry, the reserved action-vocabulary
    entries, and the KYC required-artifact standard — is declared COMPLETE here
    in Slice S1 (one version bump, 1.0.0 → 1.1.0), consumed by S2 (foreign
    plants, name-match / foreign-signal rows) and S3 (KYC gaps, insider flag)
    with no further bump — the same discipline Slice B used to declare the
    triage fields ahead of Slice C.
    """
    return {
        "version": SWEEP_VERSION,
        "flow_edge_types": ["controls", "transaction"],
        "hop_semantics": (
            "hops = minimum number of transaction edges on a directed path "
            "from the subject (its uid or any wallet it controls) to a "
            "designated address; 0 = the subject controls a designated address"
        ),
        "direct_hop_max": DIRECT_HOP_MAX,
        "adjacency_link_types": ["reused_kyc", "shared_device"],
        "name_match_threshold": NAME_MATCH_THRESHOLD,
        "hold_systems": {
            "system_of_record": "sanctions_hold_admin",
            "analytics_copy": "sanctions_hold_warehouse",
        },
        "gap_taxonomy": dict(GAP_TAXONOMY),
        "triage_order": list(TRIAGE_ORDER),
        "action_vocabulary": list(ACTION_VOCABULARY),
        "list_source_registry": {
            regime: dict(entry) for regime, entry in LIST_SOURCE_REGISTRY.items()
        },
        "required_artifacts": {
            etype: list(arts) for etype, arts in REQUIRED_ARTIFACTS.items()
        },
    }


from .designation import (  # noqa: E402
    DESIGNATION_ID_PATTERN,
    Designation,
    DesignationNameMatch,
    DesignationParseError,
    designation_from_record,
    match_designated_name,
    parse_designation,
)
from .exposure import (  # noqa: E402
    AdjacentAccount,
    ExposedAccount,
    ExposureResult,
    sweep_exposure,
)
from .verify import StatusGap, verify_block_status  # noqa: E402
from .worksheet import (  # noqa: E402
    WorksheetRow,
    assert_worksheet_resolvable,
    build_worksheet,
    worksheet_grounding_report,
)
from .escalations import (  # noqa: E402
    DRAFT_STATUS,
    EscalationDraft,
    SuppressedEscalation,
    draft_escalations,
)
from .pipeline import SweepResult, default_sweep_dir, run_sweep  # noqa: E402
from .packager import build_sweep_package, write_sweep_package  # noqa: E402

__all__ = [
    "SWEEP_VERSION",
    "NAME_MATCH_THRESHOLD",
    "DIRECT_HOP_MAX",
    "ACTION_VOCABULARY",
    "TRIAGE_ORDER",
    "GAP_TAXONOMY",
    "LIST_SOURCE_REGISTRY",
    "REQUIRED_ARTIFACTS",
    "sweep_config",
    "DESIGNATION_ID_PATTERN",
    "Designation",
    "DesignationNameMatch",
    "DesignationParseError",
    "designation_from_record",
    "match_designated_name",
    "parse_designation",
    "AdjacentAccount",
    "ExposedAccount",
    "ExposureResult",
    "sweep_exposure",
    "StatusGap",
    "verify_block_status",
    "WorksheetRow",
    "assert_worksheet_resolvable",
    "build_worksheet",
    "worksheet_grounding_report",
    "DRAFT_STATUS",
    "EscalationDraft",
    "SuppressedEscalation",
    "draft_escalations",
    "SweepResult",
    "default_sweep_dir",
    "run_sweep",
    "build_sweep_package",
    "write_sweep_package",
]
