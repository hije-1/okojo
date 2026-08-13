"""The read-only coverage-gap derivation.

``run_coverage_assessment(conn)`` reads the customer base's geographic footprint
(three separately-counted legs), joins it against the published
regime -> jurisdiction coverage policy and the frozen sweep registry's ingested
status, and returns the covered set, the two gap classes, and the
declared-but-not-ingested regimes elevated to a finding — every line carrying its
provenance. Pure and read-only: no store is mutated, no chain is written (that is
a later slice).
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..sweep import LIST_SOURCE_REGISTRY
from . import FOOTPRINT_LEGS, GAP_TAXONOMY, REGIME_JURISDICTION_COVERAGE, COVERAGE_VERSION

# Gap-class labels (re-exported for callers / tests; owned here).
GAP_NO_COVERAGE = "no_coverage"
GAP_INGESTION = "ingestion"


class FootprintLeg(BaseModel):
    """One customer-geography field, counted per jurisdiction and cited to it."""

    leg: str                       # residence | kyc_issuing | nationality
    label: str                     # investigator-facing description of the field
    count_unit: str                # "customers" | "documents"
    counts: dict[str, int]         # jurisdiction code -> count (rows with a value)
    total: int                     # rows counted (sum of counts)
    provenance: list[str]          # the source[...].field citation(s)


class JurisdictionCoverage(BaseModel):
    """The coverage verdict for one footprint jurisdiction."""

    jurisdiction: str
    covered: bool                          # >=1 INGESTED regime covers it
    ingested_regimes: list[str]            # ingested regimes covering it
    not_ingested_regimes: list[str]        # declared-but-not-ingested regimes covering it
    gap_class: Optional[str]               # None | "no_coverage" | "ingestion"
    annotation: Optional[str] = None       # e.g. the QZ/XV territory-scoping note
    provenance: list[str]                  # the coverage-policy / registry citation(s)


class CoverageAssessment(BaseModel):
    """The whole-book screening-coverage-gap finding — institution-level."""

    config_version: str
    footprint_legs: list[FootprintLeg]
    footprint_jurisdictions: list[str]     # union across the three legs, sorted
    per_jurisdiction: list[JurisdictionCoverage]
    covered_jurisdictions: list[str]
    no_coverage_gaps: list[str]
    ingestion_gaps: list[str]
    declared_not_ingested_regimes: list[str]   # regime CODES declared but not ingested
    provenance: list[str]


def _leg(rows, leg: str, label: str, count_unit: str,
         source: str, field: str) -> FootprintLeg:
    """Count one geography field per jurisdiction, skipping blanks/NaN."""
    counts: Counter = Counter()
    for r in rows:
        val = r.get(field)
        code = "" if val is None else str(val).strip()
        if not code or code.lower() == "nan":
            continue
        counts[code] += 1
    return FootprintLeg(
        leg=leg, label=label, count_unit=count_unit,
        counts=dict(sorted(counts.items())),
        total=sum(counts.values()),
        provenance=[f"{source}[*].{field}"],
    )


# Which connector accessor supplies the rows for each footprint-leg ``source``.
# The published ``FOOTPRINT_LEGS`` config names its source as a string ("accounts"
# / "kyc_docs"); this map is the ONE place that binds those names to the actual
# read, so the assessment builds its legs by iterating the config rather than
# repeating the source/field/label values inline. Adding a leg over a new source
# is a config edit here plus one entry — never a second hard-coded read.
_LEG_SOURCE_ACCESSORS = {
    "accounts": lambda conn: conn.all_accounts(),
    "kyc_docs": lambda conn: conn.all_kyc(),
}


def run_coverage_assessment(
    conn: Connectors, *,
    coverage_map: Optional[dict] = None,
    list_source_registry: Optional[dict] = None,
    footprint_legs: Optional[list] = None,
) -> CoverageAssessment:
    """Assess the customer base's footprint against enabled list coverage.

    ``coverage_map`` / ``list_source_registry`` / ``footprint_legs`` default to
    the published policy, the frozen sweep registry, and the published footprint
    configuration; all are injectable so a test can flip a regime's ingested
    status (P8-G) or add/change a footprint leg WITHOUT ever editing the frozen
    config. The legs are BUILT BY ITERATING ``footprint_legs`` (through
    ``_LEG_SOURCE_ACCESSORS``), so a config edit drives runtime behavior — the
    versioned policy is the single source of truth, not a hard-coded repeat.
    """
    coverage_map = REGIME_JURISDICTION_COVERAGE if coverage_map is None else coverage_map
    registry = LIST_SOURCE_REGISTRY if list_source_registry is None else list_source_registry
    leg_specs = FOOTPRINT_LEGS if footprint_legs is None else footprint_legs

    # Fetch each distinct source once, then build every leg from the config.
    row_cache: dict[str, list] = {}
    legs = []
    for spec in leg_specs:
        source = spec["source"]
        if source not in row_cache:
            try:
                row_cache[source] = _LEG_SOURCE_ACCESSORS[source](conn)
            except KeyError:
                raise ValueError(
                    f"footprint leg {spec.get('leg')!r} names an unknown source "
                    f"{source!r}; add it to _LEG_SOURCE_ACCESSORS"
                ) from None
        legs.append(_leg(row_cache[source], spec["leg"], spec["label"],
                         spec["count_unit"], source, spec["field"]))

    footprint = sorted(set().union(*(set(leg.counts) for leg in legs)))

    # Invert the coverage policy: jurisdiction -> regimes declaring coverage.
    covering: dict[str, list[str]] = {}
    for regime, juris in coverage_map.items():
        for j in juris:
            covering.setdefault(j, []).append(regime)

    ingested = {r for r, entry in registry.items() if entry.get("ingested")}

    # Territory annotations (Q3 rider): a footprint jurisdiction that is ALSO a
    # designated territory code or its parent country is screened via the
    # territory/geo path; here it is measured as a plain footprint jurisdiction.
    annotations = _territory_annotations(conn)

    per: list[JurisdictionCoverage] = []
    covered_set, no_cov, ingest_gaps = [], [], []
    for j in footprint:
        regimes = sorted(covering.get(j, []))
        ing = [r for r in regimes if r in ingested]
        not_ing = [r for r in regimes if r not in ingested]
        if ing:
            gap_class = None
            covered_set.append(j)
            prov = [f"coverage_config[regime_jurisdiction_coverage].{r}" for r in ing]
        elif not_ing:
            gap_class = GAP_INGESTION
            ingest_gaps.append(j)
            prov = [f"coverage_config[regime_jurisdiction_coverage].{r}" for r in not_ing]
            prov += [f"list_source_registry[{r}].ingested" for r in not_ing]
        else:
            gap_class = GAP_NO_COVERAGE
            no_cov.append(j)
            prov = ["coverage_config[regime_jurisdiction_coverage]"]
        ann = annotations.get(j)
        if ann:
            prov = prov + [ann[1]]
        per.append(JurisdictionCoverage(
            jurisdiction=j, covered=bool(ing),
            ingested_regimes=ing, not_ingested_regimes=not_ing,
            gap_class=gap_class,
            annotation=(ann[0] if ann else None),
            provenance=prov,
        ))

    declared_not_ingested = sorted(r for r, entry in registry.items()
                                   if not entry.get("ingested"))

    return CoverageAssessment(
        config_version=COVERAGE_VERSION,
        footprint_legs=legs,
        footprint_jurisdictions=footprint,
        per_jurisdiction=per,
        covered_jurisdictions=covered_set,
        no_coverage_gaps=no_cov,
        ingestion_gaps=ingest_gaps,
        declared_not_ingested_regimes=declared_not_ingested,
        provenance=[f"coverage_config[version={COVERAGE_VERSION}]"],
    )


def _territory_annotations(conn: Connectors) -> dict[str, tuple[str, str]]:
    """jurisdiction code -> (annotation text, citation) for footprint codes that
    are a designated territory or its parent country. Data-derived from
    ``territory_profile`` so the note is grounded, never hardcoded to a code."""
    out: dict[str, tuple[str, str]] = {}
    for d in conn.all_designations():
        if str(d.get("list_type")) != "territory":
            continue
        prof = conn.territory_profile_for(str(d["designation_id"]))
        if prof is None:
            continue
        did = str(d["designation_id"])
        label = str(prof["territory_label"])
        cite = f"territory_profile[{did}]"
        tcode = str(prof["territory_code"]).strip()
        ccode = str(prof["country_code"]).strip()
        if tcode:
            out[tcode] = (
                f"designated territory ({label}, {did}); also screened via the "
                f"territory/geo path — here counted only as a footprint jurisdiction",
                cite,
            )
        if ccode:
            out[ccode] = (
                f"fictional parent country of the designated {label} territory "
                f"({did}); no standing list-source regime enumerates it",
                cite,
            )
    return out
