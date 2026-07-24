"""Phase 5 Slice C: the checkers test claims against evidence, and only evidence.

Two guards carry over from Slice B and are the reason the eval means anything:

  1. **Anti-tautology.** The checkers may not read the scenario's answer key.
     ``ground_truth.json`` now carries ``rfi_claim_key``,
     ``registry_shared_officer_uids`` and ``prior_rfi_ids`` - all eval-only. A
     checker that read them would be scored against data it was handed.
  2. **Prior RFIs are evidence, never subjects.** ``SIM-RFI-0000`` is consumed
     only as a rebuttal source; it is never decomposed or adjudicated.
"""

from __future__ import annotations

import inspect

import pytest

from okojo.entity import build_backbone
from okojo.rfi import (
    MIN_CORROBORATING_SOURCES,
    SOURCE_KEYS,
    STRONG_REBUTTAL,
    VERDICTS,
    adjudicate_claim,
    check_contradictions,
    decompose,
)
from okojo.rfi import checkers as checkers_module
from okojo.rfi import contradiction as contradiction_module
from okojo.rfi.checkers import (
    Rebuttal,
    check_device,
    check_onchain,
    check_prior_rfi,
    check_registry,
    named_entities,
)


@pytest.fixture()
def backbone(conn):
    return build_backbone(conn)


@pytest.fixture()
def table(conn, trust_uid, backbone):
    return check_contradictions(conn, trust_uid, backbone)


# --------------------------------------------------------------------------- #
# Guard 1 - anti-tautology
# --------------------------------------------------------------------------- #
_ANSWER_KEY_TOKENS = (
    "ground_truth", "rfi_claim_key", "registry_shared_officer_uids",
    "prior_rfi_ids", "contradicted_by", "rfi_lies", "expected_sources",
)


@pytest.mark.parametrize("module", [checkers_module, contradiction_module])
def test_checker_modules_never_name_the_answer_key(module):
    """Fails the moment a checker reaches for eval-only data."""
    src = inspect.getsource(module)
    for token in _ANSWER_KEY_TOKENS:
        assert token not in src, f"{module.__name__} references answer-key data: {token}"


def test_checkers_read_only_evidence_accessors(conn, trust_uid, backbone):
    """Sanity: the table is produced from connectors + backbone alone."""
    d = decompose(conn, trust_uid)
    t = check_contradictions(conn, trust_uid, backbone, decomposition=d)
    assert t is not None and len(t.adjudications) == len(d.claims)
    for adj in t.adjudications:
        for r in adj.rebuttals:
            assert r.provenance, "every rebuttal carries its receipts"
            assert r.source in SOURCE_KEYS


# --------------------------------------------------------------------------- #
# Guard 2 - a prior RFI is evidence, not a subject
# --------------------------------------------------------------------------- #
def test_prior_rfi_is_never_adjudicated(table, conn, trust_uid, ground_truth):
    prior_ids = set(ground_truth["prior_rfi_ids"])
    assert table.rfi_id not in prior_ids
    assert {a.claim_id for a in table.adjudications} == {"C1", "C2", "C3", "C4"}
    # ...and P1 (the prior answer's own claim) is nowhere in the table.
    assert "P1" not in {a.claim_id for a in table.adjudications}


def test_prior_rfi_is_used_as_a_rebuttal_source(table, ground_truth):
    c2 = table.get("C2")
    prior = [r for r in c2.rebuttals if r.source == "prior_rfi"]
    assert prior, "the prior answer must rebut the denial"
    cited = {p.row_key for r in prior for p in r.provenance}
    assert cited == set(ground_truth["prior_rfi_ids"])


# --------------------------------------------------------------------------- #
# Applicability is text-driven, not id-driven
# --------------------------------------------------------------------------- #
def test_probes_are_gated_on_what_the_claim_asserts(conn, trust_uid, backbone):
    d = decompose(conn, trust_uid)
    by_id = {c.claim_id: c for c in d.claims}

    # A relationship denial reaches registry + prior_rfi; a custody assertion does not.
    assert check_registry(conn, backbone, by_id["C2"], trust_uid)
    assert not check_registry(conn, backbone, by_id["C1"], trust_uid)
    assert check_prior_rfi(conn, backbone, by_id["C2"], trust_uid)
    assert not check_prior_rfi(conn, backbone, by_id["C4"], trust_uid)

    # A custody assertion reaches device; a source-of-funds assertion does not.
    assert check_device(conn, backbone, by_id["C1"], trust_uid)
    assert not check_device(conn, backbone, by_id["C4"], trust_uid)

    # On-chain covers denial (flows) and source-of-funds, but not custody.
    assert check_onchain(conn, backbone, by_id["C2"], trust_uid)
    assert check_onchain(conn, backbone, by_id["C4"], trust_uid)
    assert not check_onchain(conn, backbone, by_id["C1"], trust_uid)

    # Nothing can test the communications-channel claim.
    for probe in (check_registry, check_prior_rfi, check_onchain, check_device):
        assert not probe(conn, backbone, by_id["C3"], trust_uid)


def test_named_entity_resolution_uses_the_shared_backbone(conn, trust_uid, backbone):
    d = decompose(conn, trust_uid)
    c2 = next(c for c in d.claims if c.claim_id == "C2")
    named = named_entities(c2, backbone, trust_uid)
    assert len(named) == 1
    assert named[0].uid != trust_uid
    assert named[0].name in c2.text
    # The subject never resolves as its own counterparty.
    assert trust_uid not in {e.uid for e in named}


def test_registry_requires_overlapping_appointments(conn, trust_uid, backbone):
    """A shared officer only rebuts if the appointments actually coincided."""
    d = decompose(conn, trust_uid)
    c2 = next(c for c in d.claims if c.claim_id == "C2")
    rebuttals = check_registry(conn, backbone, c2, trust_uid)
    assert rebuttals
    for r in rebuttals:
        assert "overlapping" in r.statement
        assert len(r.provenance) == 2, "cites both appointment rows"


# --------------------------------------------------------------------------- #
# The corroboration gate
# --------------------------------------------------------------------------- #
def _reb(source: str, strength: float) -> Rebuttal:
    from okojo.provenance import Provenance
    return Rebuttal(source=source, statement="x", strength=strength,
                    provenance=[Provenance(source="accounts", row_key="uid:1")])


def test_gate_one_strong_rebuttal_contradicts():
    assert adjudicate_claim([_reb("registry", STRONG_REBUTTAL)], "no ownership") == "contradicted"


def test_gate_two_weak_sources_corroborate():
    weak = STRONG_REBUTTAL - 0.1
    assert MIN_CORROBORATING_SOURCES == 2
    assert adjudicate_claim(
        [_reb("onchain", weak), _reb("device", weak)], "no ownership"
    ) == "contradicted"


def test_gate_one_weak_source_only_qualifies():
    weak = STRONG_REBUTTAL - 0.1
    # Two findings from the SAME surface must not self-corroborate.
    assert adjudicate_claim(
        [_reb("device", weak), _reb("device", weak)], "our own"
    ) == "qualified"


def test_gate_distinguishes_untestable_from_unrebutted():
    assert adjudicate_claim([], "no ownership or management relationship") == "uncontested"
    assert adjudicate_claim([], "we prefer email on Tuesdays") == "unverifiable"


def test_confidence_is_noisy_or_and_bounded(table):
    for adj in table.adjudications:
        assert 0.0 <= adj.confidence <= 1.0
        assert adj.verdict in VERDICTS
        if not adj.rebuttals:
            assert adj.confidence == 0.0
    # More independent evidence -> higher confidence, never certainty.
    assert table.get("C2").confidence > table.get("C1").confidence
    assert table.get("C2").confidence < 1.0


def test_table_is_deterministic(conn, trust_uid, backbone):
    a = check_contradictions(conn, trust_uid, backbone)
    b = check_contradictions(conn, trust_uid, backbone)
    assert a.model_dump() == b.model_dump()


def test_subject_without_rfi_has_no_table(conn, ground_truth, backbone):
    uid = ground_truth["privileged_redherring_uid"]
    assert check_contradictions(conn, uid, backbone) is None


def test_pipeline_attaches_the_contradiction_table(conn, trust_uid, tmp_path):
    from okojo.orchestrator import run_case
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.contradictions is not None
    assert res.rfi_decomposition is not None
    assert len(res.contradictions.contradictions) == 2
