"""Tamper-evident, append-only audit trail — Okojo's centerpiece control.

Every access, tool call, agent decision, and output is logged here with
provenance. The log is a hash chain: each record embeds the SHA-256 of the
record before it, so any retroactive edit, deletion, or reordering breaks the
chain and :meth:`AuditLog.verify` fails. This is the direct product answer to
the governance-capture failure mode this design defends against (blocked
access, vanishing records).
"""

from __future__ import annotations

from .log import GENESIS_HASH, AuditLog

__all__ = ["AuditLog", "GENESIS_HASH"]
