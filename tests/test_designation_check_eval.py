"""X1b eval — the subject-as-seed designation check, scored against the key.

The check reuses the sweep/identity/geo/agency engines read-only; this eval
pins what the CASE-side composition concludes to ``ground_truth.json`` in the
P8-A/P8-G discipline:

* **Name/variant match membership** — which case accounts match which party
  designation by name (exact set vs the answer key's union of the direct-name,
  variant, and corroboration keys). No false positives (precision 1.0).
* **Flow-exposure membership** — the subjects whose funds reach each designated
  address (exact set vs ``designation_exposed_uids``); the DECOY designation
  hits nobody.
* **Corroboration outcome** — the verdict for each planted identity persona
  (corroborated / possible / dismissed) vs ``corroboration_outcomes``.
* **Timing parity (MANDATORY)** — the check's local pre/post/timeless mirror
  equals ``designation_exposure_timing`` for every exposed (designation, uid).
  The answer key is the arbiter against drift between the mirror and the
  sweep's own helper.
* **Territory / counterparty** — geo signals surface for the geo personas and
  the core roster stays clean; the counterparty personas show a lifecycle
  state, the clean control shows none.
* **Badge state machine, live** — RED / AMBER / GREEN each demonstrated on a
  real subject.
* **P8-G** — one demonstrated falsification: removing the corroborating
  identity attributes drops the RED badge to AMBER.

The universe of candidate subjects is EVERY account (so "no false positives"
is a real claim, not a claim over a hand-picked few). Each subject's check is
computed once in a module-scoped fixture and shared, keeping the wall-clock lean.
"""

from __future__ import annotations

import csv
import shutil

import pytest

from okojo.connectors import Connectors
from okojo.designation_check import (
    BADGE_CORROBORATED,
    BADGE_NO_MATCH,
    BADGE_POSSIBLE,
    run_designation_check,
)
from okojo.designation_check.check import CORROBORATED, DISMISSED, POSSIBLE
from okojo.eval import score

_DECOY = "DES-2026-0002"
_TERRITORY = "DES-2026-0008"
_COUNTERPARTY = "DES-2026-0009"


# --------------------------------------------------------------------------- #
# Module-scoped: run the check ONCE per candidate subject (cluster = {subject}) #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def all_checks(data_dir):
    """``{uid: DesignationCheckResult}`` over EVERY account, computed once.

    Subject-scoped clusters (``{uid}``) so each result reflects that subject's
    OWN posture — the exact-set predictions below reconstruct the ledger-wide
    membership by unioning across subjects, and any spurious membership is a
    false positive the precision assertion would catch.
    """
    conn = Connectors(data_dir=data_dir)
    try:
        uids = sorted(int(a["uid"]) for a in conn.all_accounts())
        return {uid: run_designation_check(conn, uid, {uid}) for uid in uids}
    finally:
        conn.close()


@pytest.fixture(scope="module")
def party_designation_ids(data_dir):
    conn = Connectors(data_dir=data_dir)
    try:
        return [str(r["designation_id"]) for r in conn.all_designations()
                if str(r["list_type"]) != "territory"]
    finally:
        conn.close()


def _name_variant_hits(chk) -> set[str]:
    """Designation ids this subject matches by name/variant — active hit OR
    adjudicated dismissal (a dismissed collision is still a name match)."""
    out = {h.meta.designation_id for h in chk.subject_hits
           if h.match_kind in ("name", "variant")}
    out |= {d.meta.designation_id for d in chk.dismissals
            if d.match_kind in ("name", "variant")}
    return out


def _flow_designations(chk) -> set[str]:
    return {f.meta.designation_id for f in chk.flow_exposures}


# --------------------------------------------------------------------------- #
# P8-A — exact-set scorecards                                                   #
# --------------------------------------------------------------------------- #
def test_name_variant_membership_matches_gold(
        all_checks, ground_truth, party_designation_ids, capsys):
    """Which case accounts match which party designation by name/variant. The
    answer key splits the truth across three keys (direct-name, variant, and
    the corroboration verdicts — the dismissed persona lives only in the last),
    so the expected set per designation is their union."""
    name_gt = ground_truth["designation_name_match_uids"]
    variant_gt = ground_truth["identity_variant_matches"]
    corr_gt = ground_truth["corroboration_outcomes"]

    scorecard, lines = {}, []
    all_ok = True
    for did in party_designation_ids:
        expected = (set(name_gt.get(did, []))
                    | set(variant_gt.get(did, []))
                    | {int(u) for u in corr_gt.get(did, {})})
        predicted = {uid for uid, chk in all_checks.items()
                     if did in _name_variant_hits(chk)}
        s = score(predicted, expected)
        scorecard[did] = str(s)
        lines.append(f"  {did}: predicted={sorted(predicted)} gold={sorted(expected)} {s}")
        all_ok = all_ok and (s.precision == 1.0 and s.recall == 1.0 and s.fp == 0)

    with capsys.disabled():
        print("\nDesignation-check name/variant membership scorecard "
              "(subject-as-seed, exact set vs gold):")
        for ln in lines:
            print(ln)
    assert all_ok


def test_flow_exposure_membership_matches_gold(
        all_checks, ground_truth, party_designation_ids, capsys):
    exposed_gt = ground_truth["designation_exposed_uids"]
    scorecard, all_ok = [], True
    for did in party_designation_ids:
        expected = set(exposed_gt.get(did, []))
        predicted = {uid for uid, chk in all_checks.items()
                     if did in _flow_designations(chk)}
        s = score(predicted, expected)
        scorecard.append(f"  {did}: n={len(predicted)} gold={len(expected)} {s}")
        all_ok = all_ok and (s.precision == 1.0 and s.recall == 1.0 and s.fp == 0)
    with capsys.disabled():
        print("\nDesignation-check flow-exposure membership scorecard:")
        for ln in scorecard:
            print(ln)
    assert all_ok


def test_decoy_designation_hits_nobody(all_checks):
    """The DECOY (designated addresses that touch no customer) produces no
    name hit and no flow exposure for any subject."""
    for chk in all_checks.values():
        assert _DECOY not in _name_variant_hits(chk)
        assert _DECOY not in _flow_designations(chk)


def test_corroboration_outcomes_match_gold(all_checks, ground_truth, capsys):
    """Each planted identity persona reaches the gold verdict — the badge-driving
    conclusion (a corroborated hit is RED; a dismissed collision is filtered to
    a standing dismissal line and stays GREEN)."""
    corr_gt = ground_truth["corroboration_outcomes"]
    lines = []
    for did, per_uid in corr_gt.items():
        for uid_s, expected in per_uid.items():
            uid = int(uid_s)
            chk = all_checks[uid]
            observed = None
            for h in chk.subject_hits:
                if h.meta.designation_id == did and h.corroboration_outcome:
                    observed = h.corroboration_outcome
            for d in chk.dismissals:
                if d.meta.designation_id == did:
                    observed = DISMISSED
            lines.append(f"  {did} uid {uid}: observed={observed} gold={expected}")
            assert observed == expected, (did, uid, observed, expected)
    with capsys.disabled():
        print("\nDesignation-check corroboration outcomes vs gold:")
        for ln in lines:
            print(ln)


def test_timing_parity_with_gold(all_checks, ground_truth, capsys):
    """MANDATORY parity: the check's LOCAL pre/post/timeless mirror equals the
    answer key's ``designation_exposure_timing`` for every exposed (designation,
    uid). The gold is the arbiter — this is what pins the case-side mirror to
    the sweep's own helper so the two engines can never silently diverge."""
    timing_gt = ground_truth["designation_exposure_timing"]
    checked = 0
    for did, per_uid in timing_gt.items():
        for uid_s, expected in per_uid.items():
            uid = int(uid_s)
            lines = [f for f in all_checks[uid].flow_exposures
                     if f.meta.designation_id == did]
            assert lines, f"expected a flow line for {did} uid {uid}"
            assert lines[0].timing == expected, (did, uid, lines[0].timing, expected)
            checked += 1
    with capsys.disabled():
        print(f"\nDesignation-check timing parity: {checked} (designation, uid) "
              f"pairs, all == designation_exposure_timing gold")
    assert checked > 0


def test_territory_surfaces_for_geo_personas_core_stays_clean(all_checks, ground_truth):
    """The geo personas surface a territory signal live; the core roster (uid
    500000000-500000011) carries no territory data by contamination design, so
    every core subject's territory line is clean."""
    for uid in ground_truth["geo_surfaced_uids"]:
        surfaced = [t for t in all_checks[int(uid)].territory_lines if t.surfaced]
        assert surfaced, f"geo persona {uid} should surface a territory signal"
        assert surfaced[0].meta.designation_id == _TERRITORY
    core = [uid for uid in all_checks if 500_000_000 <= uid <= 500_000_011]
    assert core, "expected the core roster in the account universe"
    for uid in core:
        assert all(not t.surfaced for t in all_checks[uid].territory_lines), uid


def test_counterparty_personas_show_state_clean_control_none(all_checks, ground_truth):
    exposed = ground_truth["counterparty_exposed_uids"]
    clean = int(ground_truth["counterparty_clean_uid"])
    for uid in exposed:
        states = [c for c in all_checks[int(uid)].counterparty_states
                  if c.meta.designation_id == _COUNTERPARTY]
        assert states and states[0].state, f"exposed counterparty {uid} shows a state"
    assert not all_checks[clean].counterparty_states, "the clean control shows no state"


def test_all_three_badge_states_live(all_checks, ground_truth, trust_uid):
    """RED / AMBER / GREEN each demonstrated on a REAL subject (not constructed):
    the corroborated persona is RED, a possible-match persona is AMBER, the
    licensed-trust subject is GREEN."""
    red_uid = next(int(u) for _d, per in ground_truth["corroboration_outcomes"].items()
                   for u, o in per.items() if o == "corroborated_true_hit")
    amber_uid = next(int(u) for _d, per in ground_truth["corroboration_outcomes"].items()
                     for u, o in per.items() if o == "possible_match_needs_human")
    assert all_checks[red_uid].badge_state == BADGE_CORROBORATED
    assert all_checks[amber_uid].badge_state == BADGE_POSSIBLE
    assert all_checks[trust_uid].badge_state == BADGE_NO_MATCH


# --------------------------------------------------------------------------- #
# P8-G — demonstrated falsification (run red then green; red output quoted)     #
# --------------------------------------------------------------------------- #
def test_p8g_removing_corroborating_identity_drops_red_to_amber(
        conn, ground_truth, data_dir, tmp_path):
    """P8-G. The corroborated persona is RED because their KYC identity
    attributes corroborate the designation's published identifiers. Remove that
    one identity row and the SAME check can no longer corroborate — the true hit
    falls to an uncorroborated possible-match and the badge drops RED -> AMBER.

    (Run red first against the un-perturbed ledger, where the subject IS
    match_corroborated, so the `== BADGE_POSSIBLE` assertion fails; then green.
    The red output is quoted in the slice report.)"""
    red_uid = next(int(u) for _d, per in ground_truth["corroboration_outcomes"].items()
                   for u, o in per.items() if o == "corroborated_true_hit")

    base = run_designation_check(conn, red_uid, {red_uid})
    assert base.badge_state == BADGE_CORROBORATED

    # Perturb ONE input: copy the scenario and drop the subject's identity row.
    pert = tmp_path / "perturbed"
    shutil.copytree(data_dir, pert)
    kpath = pert / "kyc_identity_attributes.csv"
    reader = list(csv.DictReader(kpath.open(encoding="utf-8")))
    fieldnames = reader[0].keys()
    rows = [r for r in reader if int(r["uid"]) != red_uid]
    with kpath.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        w.writerows(rows)

    pconn = Connectors(data_dir=pert)
    try:
        pert_res = run_designation_check(pconn, red_uid, {red_uid})
    finally:
        pconn.close()

    # The corroboration VANISHES: no identity row -> uncorroborated possible hit.
    assert pert_res.badge_state == BADGE_POSSIBLE
    assert not any(h.corroboration_outcome == CORROBORATED
                   for h in pert_res.subject_hits)
    assert pert_res.subject_hits and all(
        h.corroboration_outcome in (None, POSSIBLE) for h in pert_res.subject_hits)
