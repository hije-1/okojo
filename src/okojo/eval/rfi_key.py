"""Evaluation-only access to the RFI answer key.

The runtime RFI view (:func:`okojo.rfi.load_rfi`) is deliberately BLIND to the
scenario's per-claim answer key: it surfaces the question, the account-holder's
response, and the decomposed claim text, but never the ground-truth labels or the
scenario-authored rebuttal notes (removed from the runtime model in the F-016
remediation, so a runtime model dump can never carry the key).

Those authoring fields still live in the generated data — ``rfi.csv``'s
``claims_json`` and ``ground_truth.json`` — because evaluation needs a known key
to score the live contradiction checker against. This module is the ONLY
sanctioned reader of them from ``claims_json``: it loads the labels straight from
the row, so the answer key reaches an eval harness without ever transiting a
runtime record. The generator and its outputs are unchanged.
"""

from __future__ import annotations

import json

from ..connectors import Connectors


def rfi_claim_answer_key(conn: Connectors, uid: int) -> list[dict]:
    """The scenario's per-claim answer key for the subject's RFI.

    Loaded straight from ``rfi.csv``'s ``claims_json`` (the authoring fields the
    runtime view drops). Each entry is ``{claim_id, text, ground_truth,
    contradicted_by}``; returns ``[]`` if the subject carries no RFI. For
    evaluation only — never wire this onto a runtime record or UI.
    """
    rfis = conn.rfi_for(uid)
    if not rfis:
        return []
    raw_claims = rfis[0].get("claims_json") or "[]"
    parsed = json.loads(raw_claims) if isinstance(raw_claims, str) else raw_claims
    return [
        {
            "claim_id": str(c.get("claim_id", "")),
            "text": str(c.get("text", "")),
            "ground_truth": str(c.get("ground_truth", "")),
            "contradicted_by": list(c.get("contradicted_by", []) or []),
        }
        for c in parsed
    ]
