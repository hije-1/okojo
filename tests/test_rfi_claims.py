"""Phase 5 Slice B: RFI claim decomposition is faithful, grounded, and blind.

"Blind" is the load-bearing property: the decomposer may not see the scenario's
per-claim labels. If it could, the contradiction eval would be scoring the
system against data the system was handed.
"""

from __future__ import annotations

import inspect

from okojo.provenance import Provenance
from okojo.rfi import claims as claims_module
from okojo.rfi import decompose, split_sentences


def test_decomposes_every_claim_from_the_narrative(conn, trust_uid):
    d = decompose(conn, trust_uid)
    assert d is not None
    assert d.rfi_id == "SIM-RFI-0001"
    assert [c.claim_id for c in d.claims] == ["C1", "C2", "C3", "C4"]
    for c in d.claims:
        assert c.text and c.source_sentence
        assert c.well_aligned, f"{c.claim_id} aligned at only {c.alignment_score}"


def test_each_claim_aligns_to_its_own_sentence(conn, trust_uid):
    """Alignment is 1:1 - no two claims collapse onto the same sentence."""
    d = decompose(conn, trust_uid)
    sentences = [c.source_sentence for c in d.claims]
    assert len(set(sentences)) == len(sentences)
    assert not d.unaligned_sentences


def test_claims_are_grounded_in_the_rfi_row(conn, trust_uid):
    d = decompose(conn, trust_uid)
    for c in d.claims:
        assert isinstance(c.provenance, Provenance)
        assert c.provenance.source == "rfi"
        assert c.provenance.row_key == d.rfi_id
        assert c.provenance.field == "response_text"


def test_extracted_claims_carry_no_scenario_labels(conn, trust_uid):
    """The extracted objects expose only the claim and where it came from."""
    d = decompose(conn, trust_uid)
    fields = set(d.claims[0].model_fields)
    assert fields == {
        "claim_id", "text", "source_sentence", "alignment_score", "provenance",
    }
    for c in d.claims:
        assert "ground_truth" not in c.model_dump()
        assert "contradicted_by" not in c.model_dump()


def test_decomposer_source_never_names_the_answer_key():
    """Anti-tautology guard, enforced against the source itself.

    A whitelist can be widened by accident; this fails the moment either label
    key is even mentioned in the module.
    """
    src = inspect.getsource(claims_module)
    assert "ground_truth" not in src
    assert "contradicted_by" not in src
    assert claims_module._CLAIM_FIELDS == ("claim_id", "text")


def test_prior_rfi_is_not_decomposed(conn, trust_uid, ground_truth):
    """Only the RFI under review is adjudicated; a prior answer is evidence."""
    d = decompose(conn, trust_uid)
    assert d.rfi_id not in ground_truth["prior_rfi_ids"]
    prior = conn.prior_rfis_for(trust_uid)
    assert prior, "the prior RFI exists as evidence"
    assert prior[0]["rfi_id"] in ground_truth["prior_rfi_ids"]


def test_account_without_rfi_decomposes_to_none(conn, ground_truth):
    assert decompose(conn, ground_truth["privileged_redherring_uid"]) is None


def test_sentence_splitting_is_deterministic():
    text = "One thing is true. Another is not! A third? Yes."
    assert split_sentences(text) == [
        "One thing is true.", "Another is not!", "A third?", "Yes.",
    ]
    assert split_sentences("   ") == []
