"""RFI reader (Phase 1 — read-only surfacing).

Loads the subject's Request-For-Information record and parses its decomposed
claims for display. This *surfaces* the RFI — the question, the account holder's
narrative response, and the scenario's declared per-claim ground-truth labels —
so an investigator can read it alongside the rest of the case.

It does NOT adjudicate: the live, claim-by-claim contradiction engine (testing
each claim against device/on-chain/registry evidence with structured pointers and
a confidence per claim) is the Phase 5 RFI Contradiction-Checker. Everything here
is a grounded read of `rfi.csv`; claim labels are scenario ground truth, not the
output of an analysis.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance


class RfiClaim(BaseModel):
    claim_id: str
    text: str
    ground_truth: str               # e.g. "false" | "partly_true_but_omits_control" | "unverifiable"
    contradicted_by: list[str] = []  # scenario-declared prose notes (present on lies)


class RfiView(BaseModel):
    rfi_id: str
    uid: int
    question: str
    response_text: str
    claims: list[RfiClaim]
    provenance: Provenance


def load_rfi(conn: Connectors, uid: int) -> Optional[RfiView]:
    """Return the subject's RFI as a structured view, or ``None`` if it has none.

    Only the licensed-trust subject carries an RFI in the Phase 1 scenario; every
    other account returns ``None``.
    """
    rfis = conn.rfi_for(uid)
    if not rfis:
        return None

    rec = rfis[0]
    raw_claims = rec.get("claims_json") or "[]"
    parsed = json.loads(raw_claims) if isinstance(raw_claims, str) else raw_claims

    claims = [
        RfiClaim(
            claim_id=str(c.get("claim_id", "")),
            text=str(c.get("text", "")),
            ground_truth=str(c.get("ground_truth", "")),
            contradicted_by=list(c.get("contradicted_by", []) or []),
        )
        for c in parsed
    ]

    return RfiView(
        rfi_id=str(rec["rfi_id"]),
        uid=int(rec["uid"]),
        question=str(rec["question"]),
        response_text=str(rec["response_text"]),
        claims=claims,
        provenance=rec.provenance,
    )
