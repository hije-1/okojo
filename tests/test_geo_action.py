"""Phase 8 Part III (U2a): the seventh bounded decision, `geo_action`.

`decide_geo_action` scores a geo totality dossier into a net presence score and
maps it to a REVIEW-tier proposal. Every test here is over CONSTRUCTED inputs
(weight-class lists + counter-evidence staleness lists) — the decision is a pure
function of those values, so it is exhaustively unit-testable without the store.
The end-to-end eval over the seven planted personas (three cases -> three
different proposals) lives in test_geo_action_eval.py (U2b).

Framing (P8-B): these assert the RULE behaves exactly as the published policy
(docs/geo-methodology.md / agency-methodology.md §7) says — signal quality
weights, the counter-evidence subtraction, the never-adds-presence discipline,
and the five bands including the scenario-dormant trade-and-withdrawal rung.
"""

from __future__ import annotations

from okojo.agency import DECISION_OUTCOMES, decide_geo_action


def _outcome(signals, counters=()):
    return decide_geo_action(1, list(signals), list(counters)).outcome


# --- the five bands, at and around every boundary ----------------------------

def test_no_action_when_nothing_scores():
    # An empty dossier nets 0 -> no_action (the account is still returned a
    # decision record, never dropped -- Rider A at the decision level).
    rec = decide_geo_action(42, [], [])
    assert rec.outcome == "no_action_totality_resolves"
    assert rec.evidence["net_presence_score"] == 0
    assert rec.evidence["uid"] == 42


def test_band_boundaries_exact():
    # N -> outcome at each inclusive band edge and one past it.
    # standard=2, high_value=3, weak=1; bands 0 / 2 / 4 / 7 / >7.
    assert _outcome(["standard"]) == "propose_edd_rfi"                       # N=2 (edge)
    assert _outcome(["high_value"]) == "propose_withdrawal_only_restriction" # N=3
    assert _outcome(["standard", "standard"]) == "propose_withdrawal_only_restriction"  # N=4 (edge)
    assert _outcome(["standard", "high_value"]) == "propose_trade_and_withdrawal_block"  # N=5
    assert _outcome(["high_value", "standard", "standard"]) == "propose_trade_and_withdrawal_block"  # N=7 (edge)
    assert _outcome(["high_value", "high_value", "standard"]) == "propose_full_block_and_escalate"   # N=8


def test_dormant_trade_and_withdrawal_band_is_reachable():
    """The trade-and-withdrawal rung is unexercised by the seven personas
    (Tomas=3 jumps to Yusuf=12); a constructed dossier lands squarely in it,
    so the declared band is a real, tested outcome and not dead policy."""
    for signals, n in [
        (["standard", "high_value"], 5),
        (["standard", "standard", "high_value"], 7),
    ]:
        rec = decide_geo_action(1, signals, [])
        assert rec.evidence["net_presence_score"] == n
        assert rec.outcome == "propose_trade_and_withdrawal_block"


# --- signal QUALITY: a distinctive locator outweighs an ordinary hit ---------

def test_vpn_slip_outweighs_ordinary_ip():
    # vpn_slip is high_value (3) -> a restriction; a lone ordinary IP is
    # standard (2) -> only an RFI. Quality, not count, moves the proposal.
    assert _outcome(["high_value"]) == "propose_withdrawal_only_restriction"
    assert _outcome(["standard"]) == "propose_edd_rfi"


def test_carrier_only_is_a_full_signal():
    # A region-exclusive carrier alone (high_value) proposes a restriction, not
    # the ambiguous RFI -- it is a full locator, never a weak hint.
    assert _outcome(["high_value"]) == "propose_withdrawal_only_restriction"


# --- counter-evidence: subtracts, degraded by staleness, never adds ----------

def test_valid_counter_evidence_fully_rebuts_a_single_signal():
    # high_value(3) - valid(3) = 0 -> no action (the totality resolves).
    assert _outcome(["high_value"], ["valid"]) == "no_action_totality_resolves"


def test_expired_counter_evidence_only_degrades_the_subtraction():
    # high_value(3) - expired(1) = 2 -> EDD RFI: the stale card cannot rebut,
    # so the honest move is to ask. This is the ambiguous traveller.
    assert _outcome(["high_value"], ["expired"]) == "propose_edd_rfi"


def test_valid_vs_expired_is_the_whole_difference():
    # The SAME single high-value signal lands on different proposals purely on
    # the counter-evidence staleness -- valid resolves it, expired does not.
    valid = _outcome(["high_value"], ["valid"])
    expired = _outcome(["high_value"], ["expired"])
    assert valid == "no_action_totality_resolves"
    assert expired == "propose_edd_rfi"
    assert valid != expired


def test_expiry_never_adds_presence():
    # A signal plus an expired counter can only be <= the signal alone; expiry
    # degrades the subtraction, it is never read as evidence of presence.
    alone = decide_geo_action(1, ["high_value"], []).evidence["net_presence_score"]
    with_expired = decide_geo_action(1, ["high_value"], ["expired"]).evidence["net_presence_score"]
    assert with_expired <= alone
    assert with_expired == 2 and alone == 3


def test_missing_counter_carries_no_weight():
    # A "missing" status subtracts nothing (a missing refresh is a control gap,
    # not counter-evidence); the signal stands at full strength.
    assert decide_geo_action(1, ["high_value"], ["missing"]).evidence["net_presence_score"] == 3


# --- the ambiguous traveller falls OUT of the rule (not special-cased) --------

def test_ambiguous_traveller_perturbation_moves_off_edd_rfi():
    """The centrepiece: the traveller is scored like any other dossier. With an
    EXPIRED foreign residency card he lands on EDD RFI; flip the card to VALID
    and the SAME rule moves the proposal OFF EDD RFI (to no_action) by
    arithmetic alone -- no branch names him. (The end-to-end version over the
    real planted dossier, run red then green, is in test_geo_action_eval.py.)"""
    traveller_signals = ["high_value"]  # the lone VPN-slip
    assert _outcome(traveller_signals, ["expired"]) == "propose_edd_rfi"
    assert _outcome(traveller_signals, ["valid"]) != "propose_edd_rfi"
    assert _outcome(traveller_signals, ["valid"]) == "no_action_totality_resolves"


# --- invariants: closed outcome set, determinism, evidence, provenance --------

def test_every_outcome_is_in_the_closed_set():
    fixtures = [
        ([], []), (["standard"], []), (["high_value"], []),
        (["standard", "high_value"], []), (["high_value", "high_value", "standard"], []),
        (["high_value"], ["valid"]), (["high_value"], ["expired"]),
    ]
    allowed = set(DECISION_OUTCOMES["geo_action"])
    for sig, ctr in fixtures:
        assert decide_geo_action(1, sig, ctr).outcome in allowed


def test_decision_is_deterministic():
    a = decide_geo_action(7, ["high_value", "standard"], ["expired"])
    b = decide_geo_action(7, ["high_value", "standard"], ["expired"])
    assert a.summary() == b.summary()


def test_evidence_records_the_arithmetic():
    rec = decide_geo_action(9, ["high_value", "standard", "weak"], ["expired"])
    ev = rec.evidence
    assert ev["signal_score"] == 6 and ev["counter_subtraction"] == 1
    assert ev["net_presence_score"] == 5
    assert rec.outcome == "propose_trade_and_withdrawal_block"


def test_provenance_passthrough_and_calibrated_language():
    rec = decide_geo_action(9, ["high_value"], ["valid"], provenance=["ip_logs:r1"])
    assert rec.provenance == ["ip_logs:r1"]
    # Calibrated throughout: a proposal for a human, never an executed action.
    assert "proposed" in rec.rationale or "no restriction is proposed" in rec.rationale
    assert "review" in rec.plain_language.lower()
