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
