"""Append-only, hash-chained audit log.

Records are newline-delimited JSON (JSONL). Each record's ``hash`` is the
SHA-256 of its own payload *including the previous record's hash* (``prev_hash``),
forming a tamper-evident chain: mutate, drop, or reorder any record and every
hash from that point on stops matching, so :meth:`AuditLog.verify` returns
``False``.

The log is intentionally simple and dependency-free. Timestamps use the real
wall clock (this is runtime provenance, not the deterministic dataset); inject a
``clock`` for reproducible tests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from ..provenance import Provenance

GENESIS_HASH = "0" * 64

# The payload fields that are hashed, in a fixed order (hash uses sorted keys).
_PAYLOAD_FIELDS = (
    "seq", "timestamp", "actor", "action", "target", "detail", "provenance", "prev_hash",
)

ProvenanceArg = Optional[Union[Provenance, Iterable[Provenance]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_citations(provenance: ProvenanceArg) -> Optional[list[str]]:
    if provenance is None:
        return None
    if isinstance(provenance, Provenance):
        provenance = [provenance]
    cites = [p.cite() for p in provenance]
    return cites or None


class AuditLog:
    """A tamper-evident, append-only JSONL audit trail."""

    def __init__(self, path: Union[str, Path], clock: Callable[[], str] = _now_iso):
        self.path = Path(path)
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._last_hash = self._tail()

    # -- hashing ------------------------------------------------------------ #
    @staticmethod
    def _digest(payload: dict) -> str:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _tail(self) -> tuple[int, str]:
        """Return (last seq, last hash) so appends resume an existing chain."""
        if not self.path.exists():
            return 0, GENESIS_HASH
        last_line = None
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if last_line is None:
            return 0, GENESIS_HASH
        rec = json.loads(last_line)
        return int(rec["seq"]), str(rec["hash"])

    # -- write -------------------------------------------------------------- #
    def append(
        self,
        actor: str,
        action: str,
        target: Optional[str] = None,
        detail: Optional[str] = None,
        provenance: ProvenanceArg = None,
    ) -> dict:
        """Append one record and return it (with its computed hash)."""
        payload = {
            "seq": self._seq + 1,
            "timestamp": self._clock(),
            "actor": actor,
            "action": action,
            "target": target,
            "detail": detail,
            "provenance": _as_citations(provenance),
            "prev_hash": self._last_hash,
        }
        record = dict(payload, hash=self._digest(payload))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._seq = payload["seq"]
        self._last_hash = record["hash"]
        return record

    # -- read / verify ------------------------------------------------------ #
    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out

    def verify(self) -> bool:
        """Recompute the chain end-to-end; ``True`` iff nothing was tampered with."""
        prev = GENESIS_HASH
        for expected_seq, rec in enumerate(self.read_all(), start=1):
            if rec.get("seq") != expected_seq:
                return False
            if rec.get("prev_hash") != prev:
                return False
            payload = {k: rec.get(k) for k in _PAYLOAD_FIELDS}
            if self._digest(payload) != rec.get("hash"):
                return False
            prev = rec["hash"]
        return True
