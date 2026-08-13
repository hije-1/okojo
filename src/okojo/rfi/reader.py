"""RFI reader (Phase 1 — read-only surfacing).

Loads the subject's Request-For-Information record and parses its decomposed
claims for display. This *surfaces* the RFI — the question, the account holder's
narrative response, and the decomposed claim text — so an investigator can read
it alongside the rest of the case.

The runtime view is deliberately BLIND to the scenario's answer key: it carries
each claim's text but NOT its ground-truth label or scenario-authored rebuttal
notes. Those authoring fields still live in the generated data (``rfi.csv``'s
``claims_json`` / ``ground_truth.json``) for evaluation, and are read there ONLY
via the eval helper ``okojo.eval.rfi_claim_answer_key`` — never surfaced on a
runtime record that a downstream integrator, notebook, or UI could mistake for a
live analytical conclusion.

It does NOT adjudicate: the live, claim-by-claim contradiction engine (testing
each claim against device/on-chain/registry evidence with structured pointers and
a confidence per claim) is the Phase 5 RFI Contradiction-Checker. Everything here
is a grounded read of `rfi.csv`.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance


class RfiClaim(BaseModel):
    # The decomposed claim as surfaced at runtime: id + text only. The scenario's
    # per-claim ground-truth label and authored rebuttal notes are intentionally
    # ABSENT here (read only via okojo.eval.rfi_claim_answer_key for evaluation),
    # so a runtime model dump can never carry the answer key.
    claim_id: str
    text: str


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
