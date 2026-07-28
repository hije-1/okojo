"""Shared fixtures: a freshly generated synthetic dataset + connectors.

The scenario is generated once per session into a temp dir (so tests never
depend on whether ``data/synthetic/`` happens to be populated), and connectors
point at it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from okojo.connectors import Connectors  # noqa: E402
from okojo.scenario import generate_scenario  # noqa: E402


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("synthetic")
    generate_scenario(out_dir=d, seed=42)
    return d


@pytest.fixture(scope="session")
def ground_truth(data_dir) -> dict:
    return json.loads((data_dir / "ground_truth.json").read_text())


@pytest.fixture()
def conn(data_dir):
    c = Connectors(data_dir=data_dir)
    yield c
    c.close()


@pytest.fixture()
def trust_uid(conn) -> int:
    return next(
        a["uid"] for a in conn.all_accounts()
        if a["role_in_ring"] == "licensed_trust_intermediary"
    )


@pytest.fixture(scope="session")
def ring(data_dir) -> dict[str, int]:
    """Persona-key -> uid, re-derived from roles in ``accounts.csv``.

    Tests must never hardcode uids; this is the one shared derivation. For
    ``employee_cutout`` — the one role held by two accounts — the FIRST-created
    (lowest-uid) account is the ring-spec EMPLOYEE; the reused-KYC second
    employee is a distinct persona.
    """
    import pandas as pd

    accounts = pd.read_csv(data_dir / "accounts.csv")

    def _uid(role: str, country: str | None = None) -> int:
        rows = accounts[accounts.role_in_ring == role]
        if country is not None:
            rows = rows[rows.residence_country == country]
        assert len(rows) >= 1, f"no account with role {role}/{country}"
        return int(rows.uid.min())

    return {
        "KINGPIN": _uid("ultimate_controller"),
        "SIBLING": _uid("family_cutout_director"),
        "EMPLOYEE": _uid("employee_cutout"),
        "TRUST": _uid("licensed_trust_intermediary"),
        "SHELL_AE": _uid("shell_trading", "AE"),
        "SHELL_TR": _uid("shell_trading", "TR"),
        "SHELL_HK": _uid("shell_trading", "HK"),
        "SHELL_NZ": _uid("shell_trading", "NZ"),
        "SHELL_CN": _uid("shell_trading", "CN"),
        "PRIVILEGED": _uid("privileged_internal_redherring"),
        "RECIDIVIST": _uid("recidivist_mule"),
    }


@pytest.fixture()
def sweep_designations(conn, ground_truth):
    """(live, decoy) validated DOMESTIC designations from the synthetic table.

    Identified structurally (the DOMESTIC ``sdn_style`` designation with a
    non-empty expected exposure is live; the other domestic one is the decoy),
    never by hardcoded id. Part I-B adds foreign ``national_ct`` plants that
    also carry exposure — those are the separate ``foreign_designations``
    fixture, so the Part-I domestic tests stay pinned to the domestic pair.
    """
    from okojo.sweep import designation_from_record

    recs = {r["designation_id"]: r for r in conn.all_designations()}
    domestic = {i: recs[i] for i in recs
                if str(recs[i]["list_type"]) == "sdn_style"}
    live_id = next(i for i in domestic
                   if ground_truth["designation_exposed_uids"][i])
    decoy_id = next(i for i in domestic
                    if not ground_truth["designation_exposed_uids"][i])
    return designation_from_record(domestic[live_id]), designation_from_record(domestic[decoy_id])


@pytest.fixture()
def foreign_designations(conn, ground_truth):
    """(lead_time, name_only) validated FOREIGN national-CT plants (Part I-B S2).

    Identified structurally via the answer key, never by hardcoded id: the
    lead-time plant is the ``national_ct`` designation with a non-empty exposure
    (3a, chain-traced); the name-only plant is the ``national_ct`` designation
    with empty addresses and a foreign name match (3b, granularity).
    """
    from okojo.sweep import designation_from_record

    # Part-II identity plants are also national_ct/signal; exclude them so this
    # stays the S2 (3a/3b) pair. The variant-screen designations live in
    # identity_variant_matches; the T2 corroboration-collision designation lives
    # only in corroboration_outcomes — exclude the union of both.
    identity_ids = (set(ground_truth["identity_variant_matches"])
                    | set(ground_truth["corroboration_outcomes"]))
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    foreign = {i: recs[i] for i in recs
               if str(recs[i]["list_type"]) == "national_ct" and i not in identity_ids}
    lead_id = next(i for i in foreign
                   if ground_truth["designation_exposed_uids"][i])
    name_only_id = next(i for i in foreign
                        if not ground_truth["designation_exposed_uids"][i])
    return (designation_from_record(foreign[lead_id]),
            designation_from_record(foreign[name_only_id]))
