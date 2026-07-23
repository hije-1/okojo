"""Hybrid advisory matcher — keyword + semantic + structured, corroboration gate."""

from __future__ import annotations

from okojo.advisory import (
    build_advisory_retriever,
    build_structured_context,
    load_advisory,
    match_advisory,
)
from okojo.advisory.embeddings import LexicalFallbackEmbedder
from okojo.advisory.matcher import JurisdictionSignal, StructuredContext
from okojo.entity import build_backbone
from okojo.provenance import Provenance
from okojo.remarks import screen_aliases

_ADV = load_advisory()


def _retriever():
    return build_advisory_retriever(_ADV, LexicalFallbackEmbedder())


def _prov(source="test", row_key="r1"):
    return Provenance(source=source, row_key=row_key)


# --- corpus now carries structured jurisdictions --------------------------- #
def test_advisory_declares_jurisdictions_and_indicators():
    assert _ADV.jurisdictions == ["IR", "AE", "HK", "SG", "CN"]
    assert _ADV.red_flag_items and all(rf.rf_id.startswith("RF-") for rf in _ADV.red_flag_items)


# --- structured context built from the shared backbone --------------------- #
def test_structured_context_from_backbone(conn):
    bb = build_backbone(conn)
    ctx = build_structured_context(bb)
    codes = {j.code for j in ctx.jurisdictions}
    # context carries the case's raw jurisdictions (advisory-agnostic); the
    # ring's AE/HK/CN (which the advisory names) are among them.
    assert {"AE", "HK", "CN"}.issubset(codes)
    for j in ctx.jurisdictions:
        assert j.provenance.source == "accounts"


# --- gate: keyword hit WITHOUT corroboration is suppressed ------------------ #
def test_keyword_without_corroboration_is_suppressed():
    docs = [("crude oil and petroleum shipment settlement", _prov("rfi", "X"))]
    empty = StructuredContext()  # no jurisdictions, no watchlist, no exposure
    assert match_advisory(docs, _ADV, structured=empty) is None


def test_keyword_with_corroboration_surfaces():
    docs = [("crude oil and petroleum shipment settlement", _prov("rfi", "X"))]
    ctx = StructuredContext(jurisdictions=[JurisdictionSignal(code="AE", provenance=_prov("accounts", "uid:1"))])
    m = match_advisory(docs, _ADV, structured=ctx)
    assert m is not None
    assert m.corroborated is True
    assert "keyword" in m.signals and "structured" in m.signals
    assert any(c.kind == "jurisdiction" for c in m.corroborators)
    assert "petroleum" in m.matched_terms


# --- semantic signal fires independently of keyword ------------------------ #
def test_semantic_fires_without_keyword():
    # A paraphrase of a shadow-banking red flag with NO advisory trigger term.
    text = "opaque ownership routed through correspondent banking to obtain dollars"
    docs = [(text, _prov("rfi", "S"))]
    ctx = StructuredContext(sanctioned_exposure=_prov("risk_scorer", "exposure"))
    m = match_advisory(docs, _ADV, retriever=_retriever(), structured=ctx)
    assert m is not None
    assert m.matched_terms == []            # keyword did NOT fire
    assert "semantic" in m.signals
    assert m.semantic_indicators            # mapped to numbered RF-* indicators
    assert m.semantic_indicators[0].rf_id.startswith("RF-")


def test_semantic_without_corroboration_is_suppressed():
    text = "opaque ownership routed through correspondent banking to obtain dollars"
    docs = [(text, _prov("rfi", "S"))]
    assert match_advisory(docs, _ADV, retriever=_retriever(), structured=StructuredContext()) is None


# --- off-topic text matches nothing even with corroboration present -------- #
def test_offtopic_text_no_primary_hit():
    docs = [("quarterly payroll disbursement for the marketing team", _prov("rfi", "P"))]
    ctx = StructuredContext(jurisdictions=[JurisdictionSignal(code="AE", provenance=_prov("accounts", "uid:1"))])
    # no keyword, no semantic hit above threshold -> no primary hit -> no match
    assert match_advisory(docs, _ADV, retriever=_retriever(), structured=ctx) is None


# --- end-to-end on the TRUST case: all three signals + corroboration ------- #
def test_full_hybrid_on_trust_case(conn, trust_uid):
    bb = build_backbone(conn)
    alias_hits = screen_aliases(conn, backbone=bb)
    watch_prov = alias_hits[0].provenance[0] if alias_hits else None
    ctx = build_structured_context(
        bb,
        watchlist_provenance=watch_prov,
        exposure_provenance=_prov("risk_scorer", "exposure"),
    )
    rfi = conn.rfi_for(trust_uid)[0]
    docs = [(rfi["response_text"], rfi.provenance)]
    m = match_advisory(docs, _ADV, retriever=_retriever(), structured=ctx)
    assert m is not None
    assert m.advisory_id == "FIN-2025-A002"
    assert m.corroborated is True
    assert set(m.signals) == {"keyword", "semantic", "structured"}
    assert m.provenance  # grounded
