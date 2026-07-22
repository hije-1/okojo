"""Sanity + determinism tests for the synthetic scenario generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from okojo.scenario import generate_scenario  # noqa: E402


@pytest.fixture()
def scenario(tmp_path):
    summary = generate_scenario(out_dir=tmp_path, seed=42)
    gt = json.loads((tmp_path / "ground_truth.json").read_text())
    return tmp_path, summary, gt


def test_all_tables_written(scenario):
    out, _, _ = scenario
    for name in [
        "accounts.csv", "kyc_docs.csv", "devices.csv", "ip_logs.csv",
        "addresses.csv", "gas_funding.csv", "transactions.csv", "rfi.csv",
        "ground_truth.json",
    ]:
        assert (out / name).exists(), f"missing {name}"


def test_reused_kyc_document_links_separate_accounts(scenario):
    out, _, gt = scenario
    # At least one KYC doc is shared by two "separate" accounts.
    assert any(len(uids) >= 2 for uids in gt["reused_kyc_docs"].values())


def test_shared_devices_present(scenario):
    _, _, gt = scenario
    assert any(len(uids) >= 2 for uids in gt["shared_devices"].values())


def test_rfi_contains_ground_truth_lies(scenario):
    _, _, gt = scenario
    assert len(gt["rfi_lies"]) >= 2
    for lie in gt["rfi_lies"]:
        assert lie["contradicted_by"], "each lie must carry contradicting evidence"


def test_betraying_remarks_reference_real_transactions(scenario):
    out, _, gt = scenario
    txs = pd.read_csv(out / "transactions.csv")
    tx_ids = set(txs["tx_id"])
    assert gt["betraying_remarks"]
    for br in gt["betraying_remarks"]:
        assert br["tx_id"] in tx_ids


def test_recidivist_cleared_prior_reviews(scenario):
    out, _, gt = scenario
    accts = pd.read_csv(out / "accounts.csv")
    for uid in gt["recidivist_uids"]:
        row = accts[accts["uid"] == uid].iloc[0]
        assert row["prior_review_count"] >= 5


def test_privileged_redherring_has_internal_tag(scenario):
    out, _, gt = scenario
    accts = pd.read_csv(out / "accounts.csv")
    row = accts[accts["uid"] == gt["privileged_redherring_uid"]].iloc[0]
    assert isinstance(row["internal_tag"], str) and "internal" in row["internal_tag"].lower()


def test_deterministic(tmp_path):
    a = generate_scenario(out_dir=tmp_path / "a", seed=42)
    b = generate_scenario(out_dir=tmp_path / "b", seed=42)
    # summaries match apart from the output path
    a.pop("output_dir"); b.pop("output_dir")
    assert a == b
    # and every generated table is byte-identical
    for name in ["accounts.csv", "transactions.csv", "ground_truth.json", "devices.csv"]:
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()
