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
    """(live, decoy) validated Designations from the synthetic table.

    Identified structurally via the answer key (the live one has a non-empty
    expected exposure), never by hardcoded id.
    """
    from okojo.sweep import designation_from_record

    recs = {r["designation_id"]: r for r in conn.all_designations()}
    live_id = next(i for i, v in ground_truth["designation_exposed_uids"].items() if v)
    decoy_id = next(i for i, v in ground_truth["designation_exposed_uids"].items() if not v)
    return designation_from_record(recs[live_id]), designation_from_record(recs[decoy_id])
