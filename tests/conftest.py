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
