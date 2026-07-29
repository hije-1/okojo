"""Mock system connectors over the synthetic scenario.

Each accessor stands in for a production system (KYC store, ledger, device/IP
intel, on-chain address book, RFI system) and returns :class:`Record` objects —
rows bound to a :class:`~okojo.provenance.Provenance` pointer, so every fact the
rest of Okojo consumes is traceable back to a specific source row.

Read-only by construction: there are no write paths here.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from ..provenance import Provenance
from .store import Record, Store, TABLES

__all__ = ["Connectors", "Store", "Record", "TABLES"]


def _clean(row: dict) -> dict:
    """Normalise pandas artefacts: NaN (empty CSV cell) -> None."""
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            v = None
        out[k] = v
    return out


class Connectors:
    """Typed, provenance-carrying accessors over the mock systems."""

    def __init__(self, store: Optional[Store] = None, data_dir: Optional[Path] = None):
        self.store = store or Store(data_dir)

    def close(self) -> None:
        self.store.close()

    # -- internal helper ---------------------------------------------------- #
    def _records(self, table: str, sql: str, params: list, key) -> list[Record]:
        recs: list[Record] = []
        for row in self.store.query(sql, params):
            row = _clean(row)
            recs.append(Record(row, Provenance(source=table, row_key=key(row))))
        return recs

    # -- accounts / KYC ----------------------------------------------------- #
    def get_account(self, uid: int) -> Optional[Record]:
        recs = self._records(
            "accounts", "SELECT * FROM accounts WHERE uid = ?", [uid],
            lambda r: f"uid:{r['uid']}",
        )
        return recs[0] if recs else None

    def all_accounts(self) -> list[Record]:
        return self._records(
            "accounts", "SELECT * FROM accounts", [],
            lambda r: f"uid:{r['uid']}",
        )

    def get_kyc(self, kyc_doc_id: str) -> Optional[Record]:
        recs = self._records(
            "kyc_docs", "SELECT * FROM kyc_docs WHERE kyc_doc_id = ?", [kyc_doc_id],
            lambda r: r["kyc_doc_id"],
        )
        return recs[0] if recs else None

    def all_kyc(self) -> list[Record]:
        return self._records(
            "kyc_docs", "SELECT * FROM kyc_docs", [],
            lambda r: r["kyc_doc_id"],
        )

    def accounts_with_kyc(self, kyc_doc_id: str) -> list[Record]:
        """All accounts opened with a given KYC document (>1 == reused-KYC tell)."""
        return self._records(
            "accounts", "SELECT * FROM accounts WHERE kyc_doc_id = ?", [kyc_doc_id],
            lambda r: f"uid:{r['uid']}",
        )

    # -- devices / IP ------------------------------------------------------- #
    def devices_for(self, uid: int) -> list[Record]:
        return self._records(
            "devices", "SELECT * FROM devices WHERE uid = ?", [uid],
            lambda r: f"{r['device_fingerprint']}:uid:{r['uid']}",
        )

    def accounts_on_device(self, device_fingerprint: str) -> list[Record]:
        """All uids seen on a device fingerprint (>1 == shared-device tell)."""
        return self._records(
            "devices", "SELECT * FROM devices WHERE device_fingerprint = ?", [device_fingerprint],
            lambda r: f"{r['device_fingerprint']}:uid:{r['uid']}",
        )

    def all_devices(self) -> list[Record]:
        return self._records(
            "devices", "SELECT * FROM devices", [],
            lambda r: f"{r['device_fingerprint']}:uid:{r['uid']}",
        )

    def ip_logs_for(self, uid: int) -> list[Record]:
        return self._records(
            "ip_logs", "SELECT * FROM ip_logs WHERE uid = ? ORDER BY timestamp", [uid],
            lambda r: f"uid:{r['uid']}@{r['timestamp']}",
        )

    def all_ip_logs(self) -> list[Record]:
        return self._records(
            "ip_logs", "SELECT * FROM ip_logs", [],
            lambda r: f"uid:{r['uid']}@{r['timestamp']}",
        )

    # -- addresses ---------------------------------------------------------- #
    def addresses_for(self, uid: int) -> list[Record]:
        return self._records(
            "addresses", "SELECT * FROM addresses WHERE controller_uid = ?", [uid],
            lambda r: r["address"],
        )

    def get_address(self, address: str) -> Optional[Record]:
        recs = self._records(
            "addresses", "SELECT * FROM addresses WHERE address = ?", [address],
            lambda r: r["address"],
        )
        return recs[0] if recs else None

    def all_addresses(self) -> list[Record]:
        return self._records(
            "addresses", "SELECT * FROM addresses", [],
            lambda r: r["address"],
        )

    def sanctioned_addresses(self) -> list[Record]:
        return self._records(
            "addresses", "SELECT * FROM addresses WHERE is_sanctioned_synthetic = TRUE", [],
            lambda r: r["address"],
        )

    # -- transactions / remarks / gas -------------------------------------- #
    def transactions_touching(self, ref: str) -> list[Record]:
        """Transactions where ``ref`` (a ``uid:...`` or an address) is either side."""
        return self._records(
            "transactions",
            "SELECT * FROM transactions WHERE from_ref = ? OR to_ref = ? ORDER BY timestamp",
            [ref, ref],
            lambda r: r["tx_id"],
        )

    def transactions_for_uid(self, uid: int) -> list[Record]:
        return self.transactions_touching(f"uid:{uid}")

    def all_transactions(self) -> list[Record]:
        return self._records(
            "transactions", "SELECT * FROM transactions ORDER BY timestamp", [],
            lambda r: r["tx_id"],
        )

    def remarks(self) -> list[Record]:
        """Transactions carrying a non-empty free-text remark (tells)."""
        return self._records(
            "transactions",
            "SELECT * FROM transactions WHERE remark IS NOT NULL AND remark <> '' ORDER BY timestamp",
            [],
            lambda r: r["tx_id"],
        )

    def gas_funds(self) -> list[Record]:
        return self._records(
            "gas_funding", "SELECT * FROM gas_funding", [],
            lambda r: f"{r['funder_address']}->{r['funded_address']}",
        )

    # -- sanctions watchlist ------------------------------------------------ #
    def sdn_list(self) -> list[Record]:
        """The synthetic SDN/alias watchlist (Tell Miner fuzzy-match target)."""
        return self._records(
            "sdn_list", "SELECT * FROM sdn_list", [],
            lambda r: r["sdn_id"],
        )

    # -- RFI ---------------------------------------------------------------- #
    def rfi_for(self, uid: int) -> list[Record]:
        return self._records(
            "rfi", "SELECT * FROM rfi WHERE uid = ?", [uid],
            lambda r: r["rfi_id"],
        )

    def all_rfis(self) -> list[Record]:
        return self._records(
            "rfi", "SELECT * FROM rfi", [],
            lambda r: r["rfi_id"],
        )

    def prior_rfis_for(self, uid: int) -> list[Record]:
        """The subject's earlier RFI answers, oldest first.

        Separate from :meth:`rfi_for` (the RFI under review) so the contradiction
        checker can test a claim against what the same subject said before.
        """
        return self._records(
            "rfi_prior", "SELECT * FROM rfi_prior WHERE uid = ? ORDER BY asked_date", [uid],
            lambda r: r["rfi_id"],
        )

    def all_prior_rfis(self) -> list[Record]:
        return self._records(
            "rfi_prior", "SELECT * FROM rfi_prior", [],
            lambda r: r["rfi_id"],
        )

    # -- designations / sanctions holds (Phase 8) ---------------------------- #
    def all_designations(self) -> list[Record]:
        """Synthetic OFAC-style designations (the remediation sweep's trigger)."""
        return self._records(
            "designations", "SELECT * FROM designations ORDER BY designation_id", [],
            lambda r: r["designation_id"],
        )

    def get_designation(self, designation_id: str) -> Optional[Record]:
        recs = self._records(
            "designations", "SELECT * FROM designations WHERE designation_id = ?",
            [designation_id],
            lambda r: r["designation_id"],
        )
        return recs[0] if recs else None

    def warehouse_holds(self) -> list[Record]:
        """Sanctions hold status per account in the analytics warehouse copy."""
        return self._records(
            "sanctions_hold_warehouse",
            "SELECT * FROM sanctions_hold_warehouse ORDER BY uid", [],
            lambda r: f"uid:{r['uid']}",
        )

    def warehouse_hold_for(self, uid: int) -> Optional[Record]:
        recs = self._records(
            "sanctions_hold_warehouse",
            "SELECT * FROM sanctions_hold_warehouse WHERE uid = ?", [uid],
            lambda r: f"uid:{r['uid']}",
        )
        return recs[0] if recs else None

    def admin_holds(self) -> list[Record]:
        """Sanctions hold status per account in the operational system of record."""
        return self._records(
            "sanctions_hold_admin",
            "SELECT * FROM sanctions_hold_admin ORDER BY uid", [],
            lambda r: f"uid:{r['uid']}",
        )

    def admin_hold_for(self, uid: int) -> Optional[Record]:
        recs = self._records(
            "sanctions_hold_admin",
            "SELECT * FROM sanctions_hold_admin WHERE uid = ?", [uid],
            lambda r: f"uid:{r['uid']}",
        )
        return recs[0] if recs else None

    # -- KYC artifacts / staff register (Phase 8 Part I-B) ------------------- #
    def kyc_artifacts(self) -> list[Record]:
        """Onboarding artifacts on file, one row per (account, artifact type)."""
        return self._records(
            "kyc_artifacts", "SELECT * FROM kyc_artifacts ORDER BY uid, artifact_type", [],
            lambda r: f"uid:{r['uid']}:{r['artifact_type']}",
        )

    def kyc_artifacts_for(self, uid: int) -> list[Record]:
        return self._records(
            "kyc_artifacts",
            "SELECT * FROM kyc_artifacts WHERE uid = ? ORDER BY artifact_type", [uid],
            lambda r: f"uid:{r['uid']}:{r['artifact_type']}",
        )

    def staff_register(self) -> list[Record]:
        """The employee-account register (conflict-of-interest monitoring)."""
        return self._records(
            "staff_register", "SELECT * FROM staff_register ORDER BY staff_id", [],
            lambda r: r["staff_id"],
        )

    # -- identity resolution (Phase 8 Part II) ------------------------------- #
    def designation_identifiers(self) -> list[Record]:
        """Identifying data a sanctions list published per designation (T2)."""
        return self._records(
            "designation_identifiers",
            "SELECT * FROM designation_identifiers ORDER BY designation_id", [],
            lambda r: r["designation_id"],
        )

    def designation_identifier_for(self, designation_id: str) -> Optional[Record]:
        recs = self._records(
            "designation_identifiers",
            "SELECT * FROM designation_identifiers WHERE designation_id = ?",
            [designation_id],
            lambda r: r["designation_id"],
        )
        return recs[0] if recs else None

    def kyc_identity_attributes(self) -> list[Record]:
        """Per-customer KYC identity attributes for identity resolution (T2)."""
        return self._records(
            "kyc_identity_attributes",
            "SELECT * FROM kyc_identity_attributes ORDER BY uid", [],
            lambda r: f"uid:{r['uid']}",
        )

    def kyc_identity_attributes_for(self, uid: int) -> Optional[Record]:
        recs = self._records(
            "kyc_identity_attributes",
            "SELECT * FROM kyc_identity_attributes WHERE uid = ?", [uid],
            lambda r: f"uid:{r['uid']}",
        )
        return recs[0] if recs else None

    # -- KYB ownership / officers (Phase 8 Part II T3) ---------------------- #
    def beneficial_ownership(self) -> list[Record]:
        """Beneficial-ownership edges (owner -> company, with stake)."""
        return self._records(
            "beneficial_ownership",
            "SELECT * FROM beneficial_ownership ORDER BY owner_uid, company_uid", [],
            lambda r: f"owner:{r['owner_uid']}:company:{r['company_uid']}",
        )

    def beneficial_ownership_for(self, company_uid: int) -> list[Record]:
        """Ownership stakes in a given company."""
        return self._records(
            "beneficial_ownership",
            "SELECT * FROM beneficial_ownership WHERE company_uid = ? "
            "ORDER BY owner_uid", [company_uid],
            lambda r: f"owner:{r['owner_uid']}:company:{r['company_uid']}",
        )

    def officer_appointments(self) -> list[Record]:
        """Corporate officer appointments (the officer/operator structure)."""
        return self._records(
            "officer_appointments",
            "SELECT * FROM officer_appointments ORDER BY appointment_id", [],
            lambda r: r["appointment_id"],
        )

    def officers_of(self, company_uid: int) -> list[Record]:
        """Officer appointments naming a given company."""
        return self._records(
            "officer_appointments",
            "SELECT * FROM officer_appointments WHERE company_uid = ? "
            "ORDER BY appointment_id", [company_uid],
            lambda r: r["appointment_id"],
        )

    # -- proximity ring (Phase 8 Part II T4) -------------------------------- #
    def relationships(self) -> list[Record]:
        """Declared-relationship metadata between customers."""
        return self._records(
            "relationships",
            "SELECT * FROM relationships ORDER BY uid_a, uid_b", [],
            lambda r: f"{r['uid_a']}:{r['uid_b']}",
        )

    def relationship_assertions(self) -> list[Record]:
        """Relationship-asserting remarks / KYC-document cross-holdings."""
        return self._records(
            "relationship_assertions",
            "SELECT * FROM relationship_assertions ORDER BY assertion_id", [],
            lambda r: r["assertion_id"],
        )

    # -- corporate registry (OSINT) ----------------------------------------- #
    def registry_for(self, uid: int) -> list[Record]:
        """Registry rows naming this uid as either the company or an officer."""
        return self._records(
            "registry",
            "SELECT * FROM registry WHERE company_uid = ? OR officer_uid = ? "
            "ORDER BY registry_id",
            [uid, uid],
            lambda r: r["registry_id"],
        )

    def registry_officers(self, company_uid: int) -> list[Record]:
        """Officers appointed to a given company."""
        return self._records(
            "registry",
            "SELECT * FROM registry WHERE company_uid = ? ORDER BY registry_id",
            [company_uid],
            lambda r: r["registry_id"],
        )

    def all_registry(self) -> list[Record]:
        return self._records(
            "registry", "SELECT * FROM registry ORDER BY registry_id", [],
            lambda r: r["registry_id"],
        )
