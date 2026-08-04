"""Screening coverage-gap check (COVERAGE, the institution-level third act).

The cross-list story so far ran per-designation and per-subject: Part I-B built
the multi-list screen; v1.1 told the investigator what was screened for *their*
subject. This asks the question for the WHOLE BOOK, and continuously —

    "Are we screening against the lists our actual customer exposure calls for?"

It measures the customer base's **geographic footprint** (residence, KYC-issuing,
and nationality jurisdictions, each a separately-counted, separately-cited leg)
against the **enabled + ingested** list-source regimes, and surfaces the mismatch
as a standing, cited *finding* — never an action. It is a **read-only derivation**
over existing data plus this published policy: it writes to no store here (the
own-chain audit trail is a later slice), re-derives no score, and reads the
frozen sweep ``LIST_SOURCE_REGISTRY`` for each regime's ingested status rather
than duplicating it, so coverage and the sweep can never disagree on what is
enabled.

Why a NEW versioned config and not an addition to ``sweep_config``: the sweep
policy is FROZEN (SWEEP 1.1.0), and the regime -> jurisdiction coverage map is a
distinct policy that deserves its own version, its own methodology doc, and its
own doc<->code anti-drift guard — the twelfth such pair.
"""

from __future__ import annotations

COVERAGE_VERSION = "1.0.0"

# Which customer-footprint jurisdictions each list-source regime is treated as an
# authoritative standing screen for. A POLICY assertion (published, tunable,
# versioned) — NOT world data: it says "a customer with nexus to jurisdiction J is
# covered, for standing-list purposes, by regime R." The ingested status of each
# regime is READ from the frozen sweep ``LIST_SOURCE_REGISTRY`` (never copied
# here), so what counts as *enabled* coverage can never drift from the sweep.
#
# Deliberately NOT exhaustive over the ISO namespace. A footprint jurisdiction
# that appears in NO regime's list here is a *no-coverage* finding — the live
# tripwire that fires the day the customer base reaches a jurisdiction this policy
# never anticipated — never a silent pass. In the current synthetic world every
# real-ISO footprint jurisdiction sits within at least the UN-style backstop's
# declared scope, so the sole no-coverage gap is ``XV`` (the fictional parent
# country of the designated Qazrun territory, surfaced only by the nationality
# leg — the value the PM's third-leg ruling adds over residence alone).
REGIME_JURISDICTION_COVERAGE = {
    "SYN-DOMESTIC-OFAC":   ["AE"],
    "SYN-FOREIGN-NCT":     ["DE", "GB", "US"],
    "SYN-UN-CONSOLIDATED": ["BR", "CN", "HK", "NZ", "QZ", "SG", "TR", "ZA"],
}

# The two gap classes. Published (visible absence of the *taxonomy*, not just of
# a list): a gap's class is always stated, so "no gap found" and "gap found, of
# this kind" are both explicit conclusions.
GAP_TAXONOMY = {
    "no_coverage": (
        "footprint jurisdiction covered by NO list-source regime at all "
        "(ingested or not); outside every declared list's scope"
    ),
    "ingestion": (
        "footprint jurisdiction covered ONLY by a declared-but-not-ingested "
        "regime; coverage exists on paper but is not enabled (visible absence)"
    ),
}

# The three footprint legs. Each is a separately-counted, separately-cited read of
# one customer-geography field; they are NOT merged into a single number, because
# an investigator reads them differently (residence = where the customer is;
# KYC-issuing = where their identity document was issued; nationality = claimed
# nationality). ``count_unit`` names what each count counts, since the KYC leg
# counts documents while the account legs count customers.
FOOTPRINT_LEGS = [
    {"leg": "residence",   "source": "accounts", "field": "residence_country",
     "label": "declared residence country", "count_unit": "customers"},
    {"leg": "kyc_issuing", "source": "kyc_docs", "field": "issuing_country",
     "label": "KYC document issuing country", "count_unit": "documents"},
    {"leg": "nationality", "source": "accounts", "field": "nationality_country",
     "label": "declared nationality", "count_unit": "customers"},
]


def coverage_config() -> dict:
    """The full, versioned coverage policy — the single source of truth.

    Stamped into the coverage assessment's own audit chain once per run (a later
    slice) and regression-tested against the published methodology doc so the two
    can never silently drift, exactly like every other versioned capability.
    """
    return {
        "version": COVERAGE_VERSION,
        "regime_jurisdiction_coverage": {
            regime: list(js) for regime, js in REGIME_JURISDICTION_COVERAGE.items()
        },
        "gap_taxonomy": dict(GAP_TAXONOMY),
        "footprint_legs": [dict(leg) for leg in FOOTPRINT_LEGS],
    }


from .assessment import (  # noqa: E402
    CoverageAssessment,
    FootprintLeg,
    JurisdictionCoverage,
    run_coverage_assessment,
)
from .pipeline import (  # noqa: E402
    CoverageAuditResult,
    default_coverage_dir,
    run_coverage_audit,
)

__all__ = [
    "COVERAGE_VERSION",
    "REGIME_JURISDICTION_COVERAGE",
    "GAP_TAXONOMY",
    "FOOTPRINT_LEGS",
    "coverage_config",
    "CoverageAssessment",
    "FootprintLeg",
    "JurisdictionCoverage",
    "run_coverage_assessment",
    "CoverageAuditResult",
    "default_coverage_dir",
    "run_coverage_audit",
]
