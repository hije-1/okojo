"""Advisory Matcher loads the ingested advisory and triggers on RFI key terms."""

from __future__ import annotations

from okojo.advisory import load_advisory, match_advisory


def test_advisory_loads_with_key_term():
    adv = load_advisory()
    assert adv.advisory_id == "FIN-2025-A002"
    assert adv.sar_key_term == "IRAN-2025-A002"
    assert adv.trigger_terms
    assert len(adv.red_flags) >= 10


def test_match_triggers_on_rfi(conn, trust_uid):
    rfi = conn.rfi_for(trust_uid)[0]
    match = match_advisory([(rfi["response_text"], rfi.provenance)])
    assert match is not None
    assert match.advisory_id == "FIN-2025-A002"
    assert "petroleum" in match.matched_terms
    assert match.provenance and match.provenance[0].source == "rfi"


def test_no_match_on_empty_text():
    assert match_advisory([("", None)]) is None
    assert match_advisory([("just a normal grocery receipt", None)]) is None
