"""Persistent case graph (Phase 6) — cases and their entities, across runs.

Every investigated case is recorded with the entities it touched (devices,
KYC documents, addresses, counterparty accounts), so the *next* case can ask
the question that cracks the documented recidivism failure mode: *has anything
about this subject been seen before?* An account that "cleared five prior
reviews" looks clean in isolation; against a persistent case graph it does
not.

Design constraints, in order:

* **Reproducible.** No timestamps anywhere in the schema; every insert comes
  from an explicitly sorted list; every read carries ``ORDER BY``. Recording
  the same sequence of cases into two fresh stores yields byte-identical
  dumps.
* **Idempotent.** ``case_id`` is derived from the subject (``case_<uid>``);
  re-running a case replaces its rows in one transaction — repeated Streamlit
  reruns can never duplicate history.
* **Read-write history is separate from read-only evidence.** Evidence lives
  in the DuckDB-backed connectors and is never mutated; case history lives
  here, in a stdlib-sqlite3 file the caller chooses (tests isolate per
  ``tmp_path``; the demo shares one store under ``data/cases/``).

Calibrated language: the case graph *surfaces* prior-history signals for
human review. It never closes, blocks, or escalates anything on its own.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors

# Bump on any change to the schema, the recidivism rule, or the entity kinds.
# Stamped into the audit trail and mirrored by the published methodology doc.
CASEGRAPH_VERSION = "1.0.0"

# An account is surfaced as a recidivism risk when its planted review history
# says it has been looked at repeatedly (>= this many prior reviews), or when
# its status IS a prior-review disposition. See docs/casegraph-methodology.md
# for the rationale behind the value.
RECIDIVISM_PRIOR_REVIEWS = 3
RECIDIVISM_STATUSES = ("retain_monitor",)

# Entity surfaces a case records (sorted; doubles as the CHECK constraint).
ENTITY_KINDS = ("address", "counterparty_account", "device", "kyc_doc")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id            TEXT PRIMARY KEY,
    subject_uid        INTEGER NOT NULL,
    subject_name       TEXT NOT NULL,
    disposition        TEXT NOT NULL,
    sar_bar_outcome    TEXT,
    decision_trace_json TEXT NOT NULL,
    audit_tip_hash     TEXT NOT NULL,
    audit_record_count INTEGER NOT NULL,
    package_sha256     TEXT
);
CREATE TABLE IF NOT EXISTS case_entities (
    case_id TEXT NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('address', 'counterparty_account', 'device', 'kyc_doc')),
    key     TEXT NOT NULL,
    PRIMARY KEY (case_id, kind, key)
);
"""


def casegraph_config() -> dict:
    """The full, versioned case-graph policy — the recidivism rule and the
    recorded entity surfaces. Single source of truth: stamped into the audit
    trail and regression-tested against the published methodology doc.
    """
    return {
        "version": CASEGRAPH_VERSION,
        "recidivism_prior_reviews": RECIDIVISM_PRIOR_REVIEWS,
        "recidivism_statuses": list(RECIDIVISM_STATUSES),
        "entity_kinds": list(ENTITY_KINDS),
        "store": "sqlite3 file; idempotent per-case upsert; no timestamps",
    }


class EntityOverlap(BaseModel):
    """One of this subject's entities previously seen in another case."""

    kind: str
    key: str
    case_ids: list[str]


class RecidivismView(BaseModel):
    """What the case graph knows about a subject at case open.

    ``is_recidivist`` is a *surfaced flag for human review*, never a
    determination: it fires on the account's own planted review history
    (``prior_review_count`` / ``account_status``) so the signal works even on
    a cold store, and the cross-case fields enrich it once history exists.
    """

    subject_uid: int
    prior_review_count: int
    account_status: str
    is_recidivist: bool
    prior_case_ids: list[str]
    entity_overlaps: list[EntityOverlap]

    def summary(self) -> dict:
        """Compact, ASCII, audit-loggable summary."""
        return {
            "subject_uid": self.subject_uid,
            "prior_review_count": self.prior_review_count,
            "account_status": self.account_status,
            "is_recidivist": self.is_recidivist,
            "prior_case_ids": self.prior_case_ids,
            "entity_overlaps": len(self.entity_overlaps),
        }


def subject_entities(conn: Connectors, subject_uid: int,
                     counterparty_uids: Optional[list[int]] = None) -> list[tuple[str, str]]:
    """The (kind, key) entity rows for one subject, explicitly sorted.

    ``counterparty_uids`` (typically the expansion's reached accounts, minus
    the subject) is optional so the read path can ask about a subject's own
    entities before any expansion exists.
    """
    rows: set[tuple[str, str]] = set()
    account = conn.get_account(subject_uid)
    if account is not None and account["kyc_doc_id"]:
        rows.add(("kyc_doc", str(account["kyc_doc_id"])))
    for dev in conn.devices_for(subject_uid):
        rows.add(("device", str(dev["device_fingerprint"])))
    for addr in conn.addresses_for(subject_uid):
        rows.add(("address", str(addr["address"])))
    for uid in counterparty_uids or []:
        if uid != subject_uid:
            rows.add(("counterparty_account", str(uid)))
    return sorted(rows)


class CaseGraphStore:
    """File-backed case graph. Connections are opened per operation (short
    transactions; Windows file-lock hygiene)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def case_id_for(subject_uid: int) -> str:
        return f"case_{subject_uid}"

    def has_case(self, subject_uid: int) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT 1 FROM cases WHERE case_id = ?",
                              (self.case_id_for(subject_uid),)).fetchone()
        return row is not None

    def record_case(
        self,
        conn: Connectors,
        subject_uid: int,
        subject_name: str,
        disposition: str,
        sar_bar_outcome: Optional[str],
        decision_trace: list[dict],
        audit_tip_hash: str,
        audit_record_count: int,
        counterparty_uids: list[int],
        package_sha256: Optional[str] = None,
    ) -> str:
        """Upsert one case and its entity rows in a single transaction."""
        case_id = self.case_id_for(subject_uid)
        entities = subject_entities(conn, subject_uid, counterparty_uids)
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO cases (case_id, subject_uid, subject_name,"
                " disposition, sar_bar_outcome, decision_trace_json, audit_tip_hash,"
                " audit_record_count, package_sha256)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, subject_uid, subject_name, disposition, sar_bar_outcome,
                 json.dumps(decision_trace), audit_tip_hash, audit_record_count,
                 package_sha256),
            )
            con.execute("DELETE FROM case_entities WHERE case_id = ?", (case_id,))
            con.executemany(
                "INSERT INTO case_entities (case_id, kind, key) VALUES (?, ?, ?)",
                [(case_id, kind, key) for kind, key in entities],
            )
        return case_id

    def open_context(self, conn: Connectors, subject_uid: int) -> RecidivismView:
        """What the graph knows about this subject at case open.

        The recidivism flag derives from the account's own review-history
        fields, so it fires even on a cold store; prior cases and cross-case
        entity overlaps enrich the picture once history exists.
        """
        account = conn.get_account(subject_uid)
        prior_reviews = int(account["prior_review_count"]) if account is not None else 0
        status = str(account["account_status"]) if account is not None else ""
        case_id = self.case_id_for(subject_uid)

        with self._connect() as con:
            prior_case_ids = [
                r[0] for r in con.execute(
                    "SELECT case_id FROM cases WHERE subject_uid = ? AND case_id != ?"
                    " ORDER BY case_id", (subject_uid, case_id)).fetchall()
            ]
            # cases (other than this one) that touched this subject's entities,
            # or named this subject as a counterparty
            overlaps: list[EntityOverlap] = []
            for kind, key in subject_entities(conn, subject_uid):
                hit_ids = [
                    r[0] for r in con.execute(
                        "SELECT case_id FROM case_entities"
                        " WHERE kind = ? AND key = ? AND case_id != ?"
                        " ORDER BY case_id", (kind, key, case_id)).fetchall()
                ]
                if hit_ids:
                    overlaps.append(EntityOverlap(kind=kind, key=key, case_ids=hit_ids))
            named_in = [
                r[0] for r in con.execute(
                    "SELECT case_id FROM case_entities"
                    " WHERE kind = 'counterparty_account' AND key = ? AND case_id != ?"
                    " ORDER BY case_id", (str(subject_uid), case_id)).fetchall()
            ]
            if named_in:
                overlaps.append(EntityOverlap(
                    kind="counterparty_account", key=str(subject_uid), case_ids=named_in,
                ))

        return RecidivismView(
            subject_uid=subject_uid,
            prior_review_count=prior_reviews,
            account_status=status,
            is_recidivist=(prior_reviews >= RECIDIVISM_PRIOR_REVIEWS
                           or status in RECIDIVISM_STATUSES),
            prior_case_ids=prior_case_ids,
            entity_overlaps=overlaps,
        )

    def dump(self) -> dict:
        """Deterministic full-store dump (reproducibility tests diff this)."""
        with self._connect() as con:
            cases = con.execute(
                "SELECT case_id, subject_uid, subject_name, disposition,"
                " sar_bar_outcome, decision_trace_json, audit_tip_hash,"
                " audit_record_count, package_sha256 FROM cases ORDER BY case_id"
            ).fetchall()
            entities = con.execute(
                "SELECT case_id, kind, key FROM case_entities"
                " ORDER BY case_id, kind, key"
            ).fetchall()
        return {"cases": cases, "case_entities": entities}
