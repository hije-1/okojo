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


# Every table the generator emits. Used by both the existence check and the
# determinism guard, so a new table can never be added without being covered.
ALL_TABLES = [
    "accounts.csv", "kyc_docs.csv", "devices.csv", "ip_logs.csv",
    "addresses.csv", "gas_funding.csv", "transactions.csv", "rfi.csv",
    "rfi_prior.csv", "registry.csv", "sdn_list.csv", "ground_truth.json",
]


def test_all_tables_written(scenario):
    out, _, _ = scenario
    for name in ALL_TABLES:
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


def test_rfi_claim_key_covers_every_claim(scenario):
    """The answer key grades all four claims, not just the declared lies.

    Without C1/C3 in the key the 'qualified' and 'unverifiable' adjudication
    branches would have no gold value to score against.
    """
    out, _, gt = scenario
    claims = json.loads(pd.read_csv(out / "rfi.csv").claims_json[0])
    key = {k["claim_id"]: k for k in gt["rfi_claim_key"]}
    assert set(key) == {c["claim_id"] for c in claims} == {"C1", "C2", "C3", "C4"}
    assert {k["verdict"] for k in gt["rfi_claim_key"]} <= {
        "contradicted", "qualified", "unverifiable", "uncontested"
    }
    # The positive class is exactly the declared lies.
    contradicted = {cid for cid, k in key.items() if k["verdict"] == "contradicted"}
    assert contradicted == {lie["claim_id"] for lie in gt["rfi_lies"]}


def test_contradicted_by_and_expected_sources_agree(scenario):
    """One-list invariant, consumer 1 vs. consumer 2.

    ``contradicted_by`` prose and ``rfi_claim_key.expected_sources`` are both
    derived from ``_RFI_CLAIM_SOURCES``; this pins them together so the two can
    never drift (the exact failure the C2 re-baseline fixed). The third consumer
    -- which checkers actually fire -- is asserted in the Phase-5 eval, which is
    where the checkers exist.
    """
    from okojo.scenario.generator import (  # noqa: PLC0415 - test-local import
        _RFI_CLAIM_SOURCES,
        _notes_for,
        _sources_for,
    )

    out, _, gt = scenario
    claims = {c["claim_id"]: c for c in json.loads(pd.read_csv(out / "rfi.csv").claims_json[0])}
    key = {k["claim_id"]: k for k in gt["rfi_claim_key"]}

    for cid in ["C1", "C2", "C3", "C4"]:
        assert key[cid]["expected_sources"] == _sources_for(cid), cid
        # contradicted_by is emitted only for declared lies; where present it is
        # exactly the prose of the same source list, in declaration order.
        if "contradicted_by" in claims[cid]:
            assert claims[cid]["contradicted_by"] == _notes_for(cid), cid
            assert claims[cid]["ground_truth"] == "false", cid

    # C2 is re-based on sources that exist in the data; the unplantable
    # reused-KYC / shared-device legs are gone for good.
    assert _sources_for("C2") == ["onchain", "prior_rfi", "registry"]
    blob = " ".join(_notes_for("C2")).lower()
    assert "reused kyc" not in blob and "device-fingerprint" not in blob
    assert _RFI_CLAIM_SOURCES["C3"] == []


def test_registry_plants_shared_director_across_denied_relationship(scenario):
    """The trust and SHELL_NZ share a director over an overlapping window."""
    out, _, gt = scenario
    reg = pd.read_csv(out / "registry.csv")
    trust_uid, nz_uid = gt["registry_shared_officer_uids"]
    rows = reg[reg.company_uid.isin([trust_uid, nz_uid])]
    officers = set(rows.officer_uid)
    assert len(officers) == 1, "one common officer across both companies"
    assert officers == {gt["ultimate_controller_uid"]}

    # Appointment windows genuinely overlap (open-ended resignation == serving).
    end = "9999-12-31"
    starts = list(rows.appointed_date)
    ends = [r if isinstance(r, str) else end for r in rows.resigned_date]
    assert max(starts) <= min(ends), "director windows must overlap"


def test_prior_rfi_self_contradicts_the_current_denial(scenario):
    """The subject's own earlier answer concedes the denied relationship."""
    out, _, gt = scenario
    prior = pd.read_csv(out / "rfi_prior.csv")
    assert list(prior.rfi_id) == gt["prior_rfi_ids"]

    accts = pd.read_csv(out / "accounts.csv")
    nz_name = accts[accts.uid == gt["registry_shared_officer_uids"][1]].entity_name.iloc[0]
    text = prior.response_text[0]
    assert nz_name in text
    assert "management services agreement" in text

    # ...and it postdates both incorporations, so it cannot name an entity that
    # did not yet exist.
    reg = pd.read_csv(out / "registry.csv")
    assert prior.asked_date[0] > reg.incorporation_date.max()


def test_c4_legs_resolve_to_planted_evidence(scenario):
    """C4 needed no planting: each declared leg maps to rows already generated."""
    out, _, gt = scenario
    txs = pd.read_csv(out / "transactions.csv")
    assert gt["sanctioned_exposure_tx_ids"], "sanctioned-exposure leg"
    assert set(gt["sanctioned_exposure_tx_ids"]) <= set(txs.tx_id)
    assert txs.is_structured_round_number.any(), "structured-transfer leg"
    assert len(pd.read_csv(out / "gas_funding.csv")) > 0, "gas-funding leg"


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
    # EVERY generated table is byte-identical — not a sample. Widened when the
    # Phase-5 tables landed so nothing can be added outside the guard.
    for name in ALL_TABLES:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_deterministic_across_hash_seeds(tmp_path):
    """Byte-stable across PYTHONHASHSEED values, not just within one process.

    ``test_deterministic`` regenerates twice inside a single interpreter, where
    the hash seed is fixed — so it cannot see set-ordering nondeterminism, which
    would pass locally and diverge on CI. This spawns two interpreters with
    different hash seeds and compares the output.
    """
    import os
    import subprocess
    import sys

    script = (
        "import sys; sys.path.insert(0, r'{src}');"
        "from okojo.scenario import generate_scenario;"
        "generate_scenario(out_dir=r'{out}', seed=42)"
    )
    src = str(Path(__file__).resolve().parents[1] / "src")
    for seed_env, sub in (("0", "h0"), ("1", "h1")):
        env = dict(os.environ, PYTHONHASHSEED=seed_env)
        out = tmp_path / sub
        subprocess.run(
            [sys.executable, "-c", script.format(src=src, out=str(out))],
            env=env, check=True,
        )
    for name in ALL_TABLES:
        assert (tmp_path / "h0" / name).read_bytes() == (tmp_path / "h1" / name).read_bytes(), name
