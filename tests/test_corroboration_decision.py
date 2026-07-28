"""Unit tests for the `corroboration` decision rule (Phase 8 Part II T2).

A pure function over two identity-attribute maps: a name/variant-matched
customer's KYC vs a designation's published identifiers. Separates a true hit
from a same-name collision, dismissing collisions WITH the reason recorded.
"""

from __future__ import annotations

from okojo.agency import DECISION_OUTCOMES, decide_corroboration


def _kyc(dob="1984-05-14", nationality="AE", doc="P-AE-000001"):
    return {"dob": dob, "nationality": nationality, "doc_type": "PASSPORT",
            "doc_number": doc}


def test_corroboration_is_a_declared_outcome_set():
    assert DECISION_OUTCOMES["corroboration"] == (
        "corroborated_true_hit", "possible_match_needs_human",
        "name_only_dismissed",
    )


def test_document_number_match_is_a_true_hit():
    d = decide_corroboration(
        101, "Yevgeniy Zhukovskiy",
        kyc=_kyc(doc="P-AE-550014"),
        identifiers=_kyc(dob="1990-01-01", nationality="RU", doc="P-AE-550014"),
    )
    # A shared document number is decisive on its own, even if softer fields differ.
    assert d.outcome == "corroborated_true_hit"
    assert d.decision_id == "corroboration"
    assert "document number" in d.evidence["matched_fields"]


def test_dob_and_nationality_match_is_a_true_hit():
    d = decide_corroboration(
        101, "Yevgeniy Zhukovskiy",
        kyc=_kyc(doc="P-AE-111111"),
        identifiers=_kyc(doc=""),  # list published no doc number -> unknown
    )
    assert d.outcome == "corroborated_true_hit"
    assert set(d.evidence["matched_fields"]) >= {"date of birth", "nationality"}


def test_two_hard_mismatches_is_a_dismissal_with_reason():
    d = decide_corroboration(
        102, "Aleksandr Volkov",
        kyc=_kyc(dob="1984-05-14", nationality="AE", doc="P-AE-770033"),
        identifiers=_kyc(dob="1970-03-22", nationality="RU", doc="P-RU-778120"),
    )
    assert d.outcome == "name_only_dismissed"
    # The dismissal records exactly which identifiers disqualified the match.
    assert d.evidence["mismatched_fields"] == [
        "date of birth", "nationality", "document number"]
    assert d.rationale and "differ" in d.rationale


def test_partial_evidence_needs_a_human():
    # Nationality matches; the list published no DOB and no doc number, so
    # nothing confirms and nothing disqualifies.
    d = decide_corroboration(
        103, "Muhammad Al-Sayigh",
        kyc=_kyc(dob="1984-05-14", nationality="AE", doc="P-AE-660021"),
        identifiers={"dob": "", "nationality": "AE", "doc_type": "", "doc_number": ""},
    )
    assert d.outcome == "possible_match_needs_human"
    assert d.evidence["mismatched_fields"] == []
    assert d.evidence["matched_fields"] == ["nationality"]


def test_absent_field_is_unknown_never_a_mismatch():
    # One hard mismatch (nationality) but DOB unknown on the list side: not two
    # mismatches, so it must NOT dismiss — it routes to a human.
    d = decide_corroboration(
        104, "Someone Else",
        kyc=_kyc(dob="1984-05-14", nationality="AE", doc=""),
        identifiers={"dob": "", "nationality": "RU", "doc_type": "", "doc_number": ""},
    )
    assert d.outcome == "possible_match_needs_human"
    assert d.evidence["field_comparison"]["dob"] == "unknown"
    assert d.evidence["field_comparison"]["nationality"] == "mismatch"


def test_rule_is_pure_and_deterministic():
    args = dict(candidate_uid=105, designated_name="X",
                kyc=_kyc(), identifiers=_kyc())
    a = decide_corroboration(**args)
    b = decide_corroboration(**args)
    assert a.summary() == b.summary()


def test_provenance_passthrough():
    d = decide_corroboration(
        106, "X", kyc=_kyc(), identifiers=_kyc(),
        provenance=["kyc_identity_attributes:uid:106", "designation_identifiers:DES-2026-0005"],
    )
    assert d.provenance == [
        "kyc_identity_attributes:uid:106", "designation_identifiers:DES-2026-0005"]
