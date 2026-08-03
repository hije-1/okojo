"""X1a — the subject-as-seed designation check (pure module over connectors).

Audit-safe by construction: ``run_designation_check`` takes only a connector +
subject + cluster and returns a value object; it writes to no chain and stamps
no config. These tests exercise the badge state-machine in isolation (constructed
inputs) and every branch of the composed check over the real synthetic personas
(uids derived structurally from the answer key / roles, never hardcoded).
"""

from __future__ import annotations

import pytest

from okojo.designation_check import (
    BADGE_CORROBORATED,
    BADGE_NO_MATCH,
    BADGE_POSSIBLE,
    DesignationMeta,
    PartyHit,
    compute_badge,
    run_designation_check,
)
from okojo.designation_check.check import CORROBORATED, DISMISSED, POSSIBLE


# --------------------------------------------------------------------------- #
# badge state-machine — pure, constructed inputs (isolation)                   #
# --------------------------------------------------------------------------- #
def _meta():
    return DesignationMeta(
        designation_id="DES-2026-0000", designated_name="Test Party",
        program="P", list_type="sdn_style", source_regime="SYN-DOMESTIC-OFAC",
        obligation_vs_signal="obligation", listed_since="2026-01-30",
        standing_phrase="a blocking-obligation list")


def _hit(outcome=None, kind="name"):
    return PartyHit(meta=_meta(), match_kind=kind, corroboration_outcome=outcome,
                    provenance=["accounts[uid:1]"])


def test_badge_green_when_no_active_hits():
    assert compute_badge([]) == BADGE_NO_MATCH


def test_badge_amber_on_uncorroborated_or_address_hit():
    assert compute_badge([_hit(outcome=None)]) == BADGE_POSSIBLE
    assert compute_badge([_hit(outcome=POSSIBLE)]) == BADGE_POSSIBLE
    assert compute_badge([_hit(kind="address")]) == BADGE_POSSIBLE


def test_badge_red_on_corroborated_true_hit():
    # Red dominates a mix of active hits.
    assert compute_badge([_hit(outcome=POSSIBLE), _hit(outcome=CORROBORATED)]) \
        == BADGE_CORROBORATED


def test_badge_never_escalated_by_dismissed_hits():
    # A dismissed collision is carried in ``dismissals``, never in
    # ``subject_hits`` — so it can never move the badge off green. This asserts
    # the contract compute_badge relies on (dismissed hits are pre-filtered).
    assert compute_badge([]) == BADGE_NO_MATCH


# --------------------------------------------------------------------------- #
# structural persona derivation from the answer key                           #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def corroborated_uid(ground_truth):
    for _des, per_uid in ground_truth["corroboration_outcomes"].items():
        for uid, outcome in per_uid.items():
            if outcome == "corroborated_true_hit":
                return int(uid)
    pytest.skip("no corroborated persona in the answer key")


@pytest.fixture()
def dismissed_uid(ground_truth):
    for _des, per_uid in ground_truth["corroboration_outcomes"].items():
        for uid, outcome in per_uid.items():
            if outcome == "name_only_dismissed":
                return int(uid)
    pytest.skip("no dismissed persona in the answer key")


@pytest.fixture()
def territory_uid(ground_truth):
    return int(ground_truth["geo_surfaced_uids"][0])


@pytest.fixture()
def counterparty_uid(ground_truth):
    return int(ground_truth["counterparty_exposed_uids"][0])


# --------------------------------------------------------------------------- #
# composed check — every branch over the real personas                        #
# --------------------------------------------------------------------------- #
def test_corroborated_persona_is_red_with_a_cited_hit(conn, corroborated_uid):
    r = run_designation_check(conn, corroborated_uid, {corroborated_uid})
    assert r.badge_state == BADGE_CORROBORATED
    reds = [h for h in r.subject_hits if h.corroboration_outcome == CORROBORATED]
    assert reds and reds[0].match_kind in ("name", "variant")
    assert reds[0].provenance  # every hit is cited


def test_dismissed_persona_is_green_with_a_standing_dismissal_line(conn, dismissed_uid):
    r = run_designation_check(conn, dismissed_uid, {dismissed_uid})
    # Adjudicated collision → GREEN, never amber (design lock Q2b).
    assert r.badge_state == BADGE_NO_MATCH
    assert not r.subject_hits          # the dismissed hit is NOT an active hit
    assert r.dismissals, "the dismissal must render as a standing visible line"
    d = r.dismissals[0]
    assert d.mismatched_fields         # the reason is recorded
    assert d.provenance                # and cited


def test_core_subject_is_green_but_carries_flow_exposure(conn, trust_uid, ground_truth):
    # The Q2(a) case: not on any list (green badge) yet funds reach a designated
    # address (a separate exposure line) — two different facts, shown separately.
    r = run_designation_check(conn, trust_uid, {trust_uid})
    assert r.badge_state == BADGE_NO_MATCH
    assert r.flow_exposures, "the trust subject has fund-flow exposure"
    # Timing is an independent read that must agree with the sweep's answer key.
    for f in r.flow_exposures:
        expected = ground_truth["designation_exposure_timing"][f.meta.designation_id][str(trust_uid)]
        assert f.timing == expected


def test_core_subject_territory_line_is_clean(conn, trust_uid):
    # Core-roster subjects carry no territory data by contamination design →
    # the clean-state assertion (persona subjects light up; see the geo test).
    r = run_designation_check(conn, trust_uid, {trust_uid})
    assert r.territory_lines, "a territory designation is always screened"
    assert all(not t.surfaced for t in r.territory_lines)
    assert all("No location signals" in t.note for t in r.territory_lines)


def test_territory_persona_lights_up_live(conn, territory_uid):
    r = run_designation_check(conn, territory_uid, {territory_uid})
    surfaced = [t for t in r.territory_lines if t.surfaced]
    assert surfaced, "the geo persona surfaces location signals live"
    assert surfaced[0].signal_ids and surfaced[0].provenance
    # Territory exposure is location evidence, never a party badge.
    assert r.badge_state == BADGE_NO_MATCH


def test_counterparty_persona_shows_lifecycle_state_display_only(conn, counterparty_uid):
    r = run_designation_check(conn, counterparty_uid, {counterparty_uid})
    assert r.counterparty_states, "an exposed counterparty subject shows its state"
    cs = r.counterparty_states[0]
    assert cs.state  # a lifecycle milestone, display-only (no proposal field exists)
    assert r.flow_exposures  # counterparty exposure is also a flow line


def test_decoy_designation_produces_no_subject_hit(conn, trust_uid, ground_truth, sweep_designations):
    _live, decoy = sweep_designations
    r = run_designation_check(conn, trust_uid, {trust_uid})
    referenced = {h.meta.designation_id for h in r.subject_hits} \
        | {f.meta.designation_id for f in r.flow_exposures}
    assert decoy.designation_id not in referenced


def test_network_notice_names_a_cluster_match(conn, trust_uid, ground_truth):
    # A name-matched account placed in the cluster surfaces as a NETWORK notice,
    # never as the subject's badge.
    des = next(d for d, uids in ground_truth["designation_name_match_uids"].items() if uids)
    match_uid = int(ground_truth["designation_name_match_uids"][des][0])
    assert match_uid != trust_uid
    r = run_designation_check(conn, trust_uid, {trust_uid, match_uid})
    notices = [n for n in r.network_notices if n.uid == match_uid and n.kind in ("name", "variant")]
    assert notices, "a cluster name match must surface as a network notice"
    assert r.badge_state == BADGE_NO_MATCH  # cluster hits never escalate the badge


def test_coverage_statement_names_declared_but_not_ingested(conn, trust_uid):
    r = run_designation_check(conn, trust_uid, {trust_uid})
    cov = r.coverage
    assert cov.designations_screened == len(conn.all_designations())
    assert cov.list_sources_screened >= 1
    assert cov.declared_not_ingested  # the UN-style consolidated list is visible-absent


def test_check_is_pure_and_repeatable(conn, trust_uid):
    a = run_designation_check(conn, trust_uid, {trust_uid})
    b = run_designation_check(conn, trust_uid, {trust_uid})
    assert a.model_dump() == b.model_dump()
