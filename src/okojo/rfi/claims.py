"""RFI claim decomposition (Phase 5, Slice B).

Turns a subject's free-text RFI response into the discrete factual assertions
that the contradiction checker can test one at a time. Two steps, both
deterministic:

1. **Split** the narrative into assertion-level sentences.
2. **Align** each of the RFI system's stored claims to the sentence it came
   from, by RapidFuzz similarity — the same matcher the Remark/Tell Miner
   already uses, so there is one fuzzy-matching dependency in the project.

Alignment is what makes the decomposition auditable: every extracted claim
points at the span of the response it was drawn from, and carries the score
that justified the pairing. A claim whose best sentence scores below
:data:`MIN_ALIGNMENT` is still emitted — surfaced with a low score for analyst
review, never silently dropped — and any sentence no claim matched is reported
in ``unaligned_sentences`` rather than discarded.

**Anti-tautology contract.** Only :data:`_CLAIM_FIELDS` are read off a stored
claim. The scenario's per-claim labels (its declared truth value and its
declared rebuttals) are answer-key data for the *eval*; if the decomposer or the
checkers could see them, the eval would be scoring the system against data the
system was handed. This module therefore never names those keys at all, and
``tests/test_rfi_claims.py`` asserts that by inspecting this file's source.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

from ..connectors import Connectors
from ..provenance import Provenance

# The ONLY keys read off a stored claim. Anything else a claim row carries -
# including the scenario's labels - is deliberately out of reach here.
_CLAIM_FIELDS = ("claim_id", "text")

# Sentence boundary: terminal punctuation followed by whitespace. The synthetic
# RFI narratives carry no abbreviations, so this needs no exception list.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Below this similarity a claim is emitted but marked weakly aligned, so a
# decomposition that drifts from the narrative is visible rather than silent.
MIN_ALIGNMENT = 60.0


class ExtractedClaim(BaseModel):
    """One discrete assertion, bound to the response text it was drawn from."""

    claim_id: str
    text: str
    source_sentence: str
    alignment_score: float
    provenance: Provenance

    @property
    def well_aligned(self) -> bool:
        return self.alignment_score >= MIN_ALIGNMENT


class RfiDecomposition(BaseModel):
    """The RFI under review, broken into testable claims."""

    rfi_id: str
    uid: int
    claims: list[ExtractedClaim]
    unaligned_sentences: list[str] = []

    def claim(self, claim_id: str) -> Optional[ExtractedClaim]:
        return next((c for c in self.claims if c.claim_id == claim_id), None)

    def summary(self) -> dict:
        """Compact, ASCII, audit-loggable summary."""
        return {
            "rfi_id": self.rfi_id,
            "claims": len(self.claims),
            "weakly_aligned": sum(1 for c in self.claims if not c.well_aligned),
            "unaligned_sentences": len(self.unaligned_sentences),
        }


def split_sentences(text: str) -> list[str]:
    """Assertion-level sentences, in narrative order."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text).strip()) if s.strip()]


def _stored_claims(raw: object) -> list[dict]:
    """Parse the RFI row's claim list down to the whitelisted fields only."""
    parsed = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [{k: str(c.get(k, "")) for k in _CLAIM_FIELDS} for c in parsed]


def decompose(conn: Connectors, uid: int) -> Optional[RfiDecomposition]:
    """Decompose the subject's RFI under review, or ``None`` if it has none.

    Only the RFI under review is decomposed. A *prior* RFI is evidence the
    checker tests claims against, never itself a subject of adjudication, so it
    is not read here.
    """
    rfis = conn.rfi_for(uid)
    if not rfis:
        return None
    rec = rfis[0]

    sentences = split_sentences(rec["response_text"])
    claims: list[ExtractedClaim] = []
    matched: set[int] = set()

    for stored in _stored_claims(rec.get("claims_json")):
        best_i, best_score = -1, 0.0
        for i, sentence in enumerate(sentences):
            # token_set_ratio tolerates the reordering and elision between a
            # narrative sentence and its canonical claim form.
            score = fuzz.token_set_ratio(stored["text"], sentence)
            if score > best_score:
                best_i, best_score = i, score
        if best_i >= 0:
            matched.add(best_i)
        claims.append(ExtractedClaim(
            claim_id=stored["claim_id"],
            text=stored["text"],
            source_sentence=sentences[best_i] if best_i >= 0 else "",
            alignment_score=round(float(best_score), 2),
            provenance=Provenance(
                source="rfi",
                row_key=str(rec["rfi_id"]),
                field="response_text",
                detail=f"claim {stored['claim_id']} decomposed from the RFI narrative",
            ),
        ))

    return RfiDecomposition(
        rfi_id=str(rec["rfi_id"]),
        uid=int(rec["uid"]),
        claims=claims,
        unaligned_sentences=[s for i, s in enumerate(sentences) if i not in matched],
    )
