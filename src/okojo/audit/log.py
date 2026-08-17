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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from ..provenance import Provenance

GENESIS_HASH = "0" * 64

# The payload fields that are hashed, in a fixed order (hash uses sorted keys).
_PAYLOAD_FIELDS = (
    "seq", "timestamp", "actor", "action", "target", "detail", "provenance", "prev_hash",
)

# Reviewer disposition — a human decision written INTO the same tamper-evident
# chain as the agent's work (v1). The two dispositions are fixed by ruling; a
# disposition is *recorded and surfaced only* — it re-runs nothing and mutates
# no case state. The record is the feature.
REVIEWER_ACTOR = "human_reviewer"
REVIEWER_ACTION = "reviewer_disposition"
REVIEWER_DISPOSITIONS = ("Approve", "Review Needed")


class DispositionError(ValueError):
    """Raised when a reviewer disposition is malformed.

    Fires on an unknown disposition or an empty/whitespace-only rationale — the
    required-rationale gate is enforced here, at the point the record is built,
    so an ungrounded human decision can never enter the chain (invariant i).
    """


@dataclass(frozen=True)
class ChainVerification:
    """The located result of verifying a hash chain.

    ``verify()`` answers *whether* a chain is intact; this answers *where* it
    first breaks, so a reader (e.g. the Audit Narrator) can report the break at
    the exact record. Read-only — computing it never touches the write path.
    """

    ok: bool
    verified_count: int          # leading records that fully verified before any break
    break_seq: Optional[int] = None   # 1-based position where verification first fails
    reason: Optional[str] = None      # "seq_out_of_order" | "prev_hash_mismatch" | "hash_mismatch"


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
        """Recompute the chain end-to-end; ``True`` iff nothing was tampered with.

        Preserved verbatim as the boolean entry point; it now delegates to
        :meth:`verify_chain_located` so the located and boolean checks share one
        definition of "intact" and can never disagree.
        """
        return self.verify_chain_located().ok

    def verify_chain_located(self) -> ChainVerification:
        """Verify the chain and report *where* it first breaks (read-only)."""
        return verify_records(self.read_all())


def build_reviewer_disposition_record(
    records: Iterable[dict],
    *,
    subject_uid: int,
    package_sha256: str,
    disposition: str,
    rationale: str,
    reviewer: str,
    timestamp: str,
    packaged_seq: Optional[int] = None,
) -> dict:
    """Compute the next hash-chained record for a human reviewer's disposition.

    Pure and disk-free, the write-path analogue of :func:`verify_records`: it
    reads an already-read chain (a list of record dicts) and returns a NEW
    record chained onto the tip, writing to NO file. The session-sandbox path
    (the public demo) uses this to append a disposition to a *session-local copy*
    of a chain — the canonical bytes on disk are never touched (invariant iii).

    The payload carries everything a reviewer decision needs: the subject uid,
    the package SHA-256 being decided on, the disposition, the required free-text
    rationale, a reviewer label, and the timestamp — hash-chained like every
    other record. ``rationale`` is REQUIRED: an empty or whitespace-only
    rationale raises :class:`DispositionError`, so the record cannot be built
    (invariant i). ``disposition`` must be one of :data:`REVIEWER_DISPOSITIONS`.

    When ``packaged_seq`` is given, the record cites the ``packaged`` chain
    record whose SHA-256 it decides on (grounding provenance); the record's own
    ``(seq, hash)`` is what the Audit Narrator grounds each sentence to.
    """
    if disposition not in REVIEWER_DISPOSITIONS:
        raise DispositionError(
            f"disposition must be one of {REVIEWER_DISPOSITIONS}, got {disposition!r}")
    clean_rationale = " ".join((rationale or "").split())
    if not clean_rationale:
        raise DispositionError("a reviewer disposition requires a non-empty rationale")

    records = list(records)
    prev_hash = str(records[-1]["hash"]) if records else GENESIS_HASH
    seq = (int(records[-1]["seq"]) + 1) if records else 1
    provenance: ProvenanceArg = None
    if packaged_seq is not None:
        provenance = [Provenance(
            source="audit_chain", row_key=f"seq:{packaged_seq}",
            detail="the packaged record whose SHA-256 this disposition decides on",
        )]
    payload = {
        "seq": seq,
        "timestamp": timestamp,
        "actor": REVIEWER_ACTOR,
        "action": REVIEWER_ACTION,
        "target": f"uid:{subject_uid}",
        "detail": json.dumps(
            {
                "subject_uid": subject_uid,
                "package_sha256": package_sha256,
                "disposition": disposition,
                "rationale": clean_rationale,
                "reviewer": reviewer,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ),
        "provenance": _as_citations(provenance),
        "prev_hash": prev_hash,
    }
    return dict(payload, hash=AuditLog._digest(payload))


def verify_records(records: Iterable[dict]) -> ChainVerification:
    """Verify an already-read list of chain records, locating the first break.

    Pure and read-only: the same recompute as :meth:`AuditLog.verify`, tracking
    the first record whose seq, ``prev_hash``, or recomputed ``hash`` fails. On
    the first failure it returns immediately (content at or beyond a broken link
    is untrustworthy, so it is neither checked nor reported). ``break_seq`` is the
    1-based position of that record; ``verified_count`` is how many leading
    records verified before it.
    """
    prev = GENESIS_HASH
    verified = 0
    for expected_seq, rec in enumerate(records, start=1):
        if rec.get("seq") != expected_seq:
            return ChainVerification(False, verified, expected_seq, "seq_out_of_order")
        if rec.get("prev_hash") != prev:
            return ChainVerification(False, verified, expected_seq, "prev_hash_mismatch")
        payload = {k: rec.get(k) for k in _PAYLOAD_FIELDS}
        if AuditLog._digest(payload) != rec.get("hash"):
            return ChainVerification(False, verified, expected_seq, "hash_mismatch")
        prev = rec["hash"]
        verified += 1
    return ChainVerification(True, verified, None, None)
