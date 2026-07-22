"""DuckDB-backed store over the synthetic scenario CSVs.

The generator (``scripts/generate_scenario.py``) writes eight CSVs to
``data/synthetic/``. This module loads them into an in-memory DuckDB instance
(via pandas, so column dtypes are predictable) and exposes a thin query API.

This is the *mock internal systems* layer of Phase 1: instead of connecting to
a real KYC store / ledger / device-intel feed, the connectors read these tables.
Everything is read-only — Okojo never mutates the evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import duckdb
import pandas as pd

from ..config import SYNTHETIC_DIR
from ..provenance import Provenance

# Logical table name -> CSV filename produced by the generator.
TABLES: dict[str, str] = {
    "accounts": "accounts.csv",
    "kyc_docs": "kyc_docs.csv",
    "devices": "devices.csv",
    "ip_logs": "ip_logs.csv",
    "addresses": "addresses.csv",
    "gas_funding": "gas_funding.csv",
    "transactions": "transactions.csv",
    "rfi": "rfi.csv",
    "sdn_list": "sdn_list.csv",
}


class Record:
    """A single evidence row bound to its :class:`Provenance` pointer.

    Behaves like a read-only mapping over the row's columns (``rec["field"]``)
    while carrying the provenance needed to satisfy the grounding contract.
    """

    __slots__ = ("data", "provenance")

    def __init__(self, data: dict[str, Any], provenance: Provenance):
        self.data = data
        self.provenance = provenance

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Record({self.provenance.cite()}, {self.data!r})"


class Store:
    """In-memory DuckDB over the synthetic CSVs."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else SYNTHETIC_DIR
        missing = [fn for fn in TABLES.values() if not (self.data_dir / fn).exists()]
        if missing:
            raise FileNotFoundError(
                f"Synthetic data not found in {self.data_dir} (missing: {missing}). "
                "Run `python scripts/generate_scenario.py` first."
            )

        self.con = duckdb.connect(database=":memory:")
        self._frames: dict[str, pd.DataFrame] = {}
        for name, fname in TABLES.items():
            df = pd.read_csv(self.data_dir / fname)
            self._frames[name] = df
            # Register the DataFrame as a DuckDB view for SQL access.
            self.con.register(name, df)

    def frame(self, name: str) -> pd.DataFrame:
        """Direct access to a loaded table as a pandas DataFrame."""
        return self._frames[name]

    def query(self, sql: str, params: Optional[list] = None) -> list[dict]:
        """Run SQL and return rows as a list of column->value dicts."""
        rel = self.con.execute(sql, params or [])
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, row)) for row in rel.fetchall()]

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
