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

SWEEP_VERSION = "1.0.0"

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
# Consumed by the triage/worksheet stage (Slice C); declared complete here so
# the version does not bump mid-phase.
ACTION_VOCABULARY = [
    "proposes_designation_hold_review",
    "flags_reconciliation_gap",
    "proposes_confirm_existing_hold",
    "flags_internal_tag_for_review",
    "flags_for_review_non_flow_linkage",
]

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
    published methodology doc so the two can never silently drift. Declared
    COMPLETE for Phase 8 Part I here in Slice B — the triage fields are
    consumed by Slice C — so no mid-phase version bump is needed.
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

__all__ = [
    "SWEEP_VERSION",
    "NAME_MATCH_THRESHOLD",
    "DIRECT_HOP_MAX",
    "ACTION_VOCABULARY",
    "TRIAGE_ORDER",
    "GAP_TAXONOMY",
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
]
