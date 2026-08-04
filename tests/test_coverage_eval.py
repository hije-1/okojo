"""COVERAGE eval — the institution-level screening coverage-gap check, scored.

The assessment is a read-only derivation over the customer footprint and the
published coverage policy; this eval pins what it concludes to
``ground_truth.json`` in the P8-A / P8-G discipline:

* **Footprint** — the union of the three legs (residence + KYC-issuing +
  nationality) equals the answer key's jurisdiction set exactly.
* **Coverage / gap membership** — the covered set, the ingestion-gap set, and
  the no-coverage-gap set each equal their answer key exactly; the three
  partition the footprint (disjoint, exhaustive).
* **Declared-but-not-ingested** — the elevated-to-finding regime set matches.
* **Grounding** — every leg and every per-jurisdiction verdict carries
  provenance; gap rows cite the registry's ingested flag; the QZ/XV territory
  rows cite ``territory_profile``.
* **P8-G** — two demonstrated falsifications: ingesting the UN-style backstop
  collapses the ingestion-gap set; de-ingesting the domestic regime moves AE
  out of the covered set. The answer key is the arbiter against drift.

The gold keys are hand-authored in the generator, independent of
``coverage_config`` (never imported there), so this is a real check.
"""

from __future__ import annotations

import copy

from okojo.coverage import run_coverage_assessment
from okojo.coverage.assessment import GAP_INGESTION, GAP_NO_COVERAGE
from okojo.sweep import LIST_SOURCE_REGISTRY


# ---- P8-A: exact-set membership --------------------------------------------- #

def test_footprint_jurisdictions_exact(conn, ground_truth):
    a = run_coverage_assessment(conn)
    assert a.footprint_jurisdictions == sorted(
        ground_truth["coverage_footprint_jurisdictions"]
    )


def test_covered_set_exact(conn, ground_truth):
    a = run_coverage_assessment(conn)
    assert a.covered_jurisdictions == sorted(
        ground_truth["coverage_covered_jurisdictions"]
    )


def test_ingestion_gaps_exact(conn, ground_truth):
    a = run_coverage_assessment(conn)
    assert a.ingestion_gaps == sorted(ground_truth["coverage_ingestion_gaps"])


def test_no_coverage_gaps_exact(conn, ground_truth):
    """The nationality leg surfaces XV — the one jurisdiction no regime lists."""
    a = run_coverage_assessment(conn)
    assert a.no_coverage_gaps == sorted(ground_truth["coverage_no_coverage_gaps"])


def test_declared_not_ingested_exact(conn, ground_truth):
    a = run_coverage_assessment(conn)
    assert a.declared_not_ingested_regimes == sorted(
        ground_truth["coverage_declared_not_ingested_regimes"]
    )


def test_gap_classes_partition_the_footprint(conn):
    """Covered / ingestion-gap / no-coverage-gap are disjoint and exhaustive."""
    a = run_coverage_assessment(conn)
    covered = set(a.covered_jurisdictions)
    ingest = set(a.ingestion_gaps)
    nocov = set(a.no_coverage_gaps)
    assert covered.isdisjoint(ingest)
    assert covered.isdisjoint(nocov)
    assert ingest.isdisjoint(nocov)
    assert covered | ingest | nocov == set(a.footprint_jurisdictions)
    # And the per-jurisdiction rows agree with the roll-up sets.
    for jc in a.per_jurisdiction:
        if jc.jurisdiction in covered:
            assert jc.covered and jc.gap_class is None
        elif jc.jurisdiction in ingest:
            assert not jc.covered and jc.gap_class == GAP_INGESTION
        else:
            assert not jc.covered and jc.gap_class == GAP_NO_COVERAGE


# ---- footprint legs (three, labeled, counts recomputed) --------------------- #

def test_three_footprint_legs_labeled_and_grounded(conn):
    a = run_coverage_assessment(conn)
    assert [leg.leg for leg in a.footprint_legs] == [
        "residence", "kyc_issuing", "nationality"
    ]
    for leg in a.footprint_legs:
        assert leg.label and leg.count_unit in {"customers", "documents"}
        assert leg.provenance and all(p for p in leg.provenance)
        assert leg.total == sum(leg.counts.values())


def test_footprint_counts_recomputed_from_data(conn):
    """Independent recompute of each leg's counts straight from the store."""
    a = run_coverage_assessment(conn)
    by_leg = {leg.leg: leg.counts for leg in a.footprint_legs}

    def _count(rows, field):
        from collections import Counter
        c = Counter()
        for r in rows:
            v = r.get(field)
            s = "" if v is None else str(v).strip()
            if s and s.lower() != "nan":
                c[s] += 1
        return dict(c)

    accounts, kyc = conn.all_accounts(), conn.all_kyc()
    assert by_leg["residence"] == _count(accounts, "residence_country")
    assert by_leg["kyc_issuing"] == _count(kyc, "issuing_country")
    assert by_leg["nationality"] == _count(accounts, "nationality_country")


# ---- grounding -------------------------------------------------------------- #

def test_every_verdict_and_gap_row_is_grounded(conn):
    a = run_coverage_assessment(conn)
    for jc in a.per_jurisdiction:
        assert jc.provenance, f"{jc.jurisdiction} carries no provenance"
        if jc.gap_class == GAP_INGESTION:
            assert any("ingested" in p for p in jc.provenance), (
                f"{jc.jurisdiction} ingestion-gap must cite the registry flag"
            )


def test_territory_rows_annotated_and_cited(conn):
    """QZ (a designated territory) and XV (its parent country) carry the
    territory-scoping annotation, cited to territory_profile."""
    a = run_coverage_assessment(conn)
    rows = {jc.jurisdiction: jc for jc in a.per_jurisdiction}
    for code in ("QZ", "XV"):
        assert code in rows, f"{code} expected in the footprint"
        assert rows[code].annotation, f"{code} must carry a territory annotation"
        assert any("territory_profile" in p for p in rows[code].provenance)


# ---- P8-G: falsification ---------------------------------------------------- #

def test_p8g_ingesting_un_backstop_collapses_ingestion_gaps(conn, ground_truth):
    """Flip SYN-UN-CONSOLIDATED to ingested — via an INJECTED registry copy, never
    editing the frozen sweep_config — and the ingestion-gap set must empty (its
    eight jurisdictions become covered)."""
    baseline = run_coverage_assessment(conn)
    assert baseline.ingestion_gaps == sorted(ground_truth["coverage_ingestion_gaps"])

    reg = copy.deepcopy(dict(LIST_SOURCE_REGISTRY))
    reg["SYN-UN-CONSOLIDATED"]["ingested"] = True
    flipped = run_coverage_assessment(conn, list_source_registry=reg)

    assert flipped.ingestion_gaps == [], (
        "ingesting the backstop must clear every ingestion gap"
    )
    # Those eight jurisdictions are now covered; XV (no regime) stays a gap.
    assert set(ground_truth["coverage_ingestion_gaps"]).issubset(
        set(flipped.covered_jurisdictions)
    )
    assert flipped.no_coverage_gaps == baseline.no_coverage_gaps
    # And the frozen registry itself was never mutated.
    assert LIST_SOURCE_REGISTRY["SYN-UN-CONSOLIDATED"]["ingested"] is False


def test_p8g_deingesting_domestic_moves_ae_out_of_covered(conn):
    """De-ingest SYN-DOMESTIC-OFAC (injected copy) and AE — covered only by it —
    must fall out of the covered set into an ingestion gap."""
    baseline = run_coverage_assessment(conn)
    assert "AE" in baseline.covered_jurisdictions

    reg = copy.deepcopy(dict(LIST_SOURCE_REGISTRY))
    reg["SYN-DOMESTIC-OFAC"]["ingested"] = False
    flipped = run_coverage_assessment(conn, list_source_registry=reg)

    assert "AE" not in flipped.covered_jurisdictions
    assert "AE" in flipped.ingestion_gaps
    assert LIST_SOURCE_REGISTRY["SYN-DOMESTIC-OFAC"]["ingested"] is True
