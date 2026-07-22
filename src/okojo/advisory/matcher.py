"""Regulatory Advisory Matcher (Phase 1 — keyword/regex).

Loads one ingested FinCEN advisory (the committed key-terms extract) and matches
its trigger terms against case text — chiefly the subject's RFI response. On a
hit it attaches the advisory, the specific red-flag indicators, and the exact
SAR key term FinCEN instructs filers to cite.

Phase 1 is keyword/regex only. Semantic/embedding retrieval and the
corroboration threshold (key-term hit + >=1 structured corroborator) arrive in
Phase 3 — until then this deliberately surfaces on a single key-term hit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel

from ..provenance import Provenance

_DEFAULT_CORPUS = Path(__file__).parent / "corpus" / "iran_oil_keyterms.md"


class Advisory(BaseModel):
    advisory_id: str
    title: str
    source: str
    sar_key_term: str
    sar_fields: str
    trigger_terms: list[str]
    red_flags: list[str]


class AdvisoryMatch(BaseModel):
    advisory_id: str
    title: str
    sar_key_term: str
    sar_fields: str
    matched_terms: list[str]
    red_flags: list[str]
    provenance: list[Provenance]


def _parse_meta(text: str, label: str) -> str:
    m = re.search(rf"-\s*\*\*{re.escape(label)}:\*\*\s*(.+)", text)
    return m.group(1).strip() if m else ""


def load_advisory(path: Optional[Path] = None) -> Advisory:
    path = Path(path) if path else _DEFAULT_CORPUS
    text = path.read_text(encoding="utf-8")

    title = text.splitlines()[0].lstrip("# ").strip()

    # Trigger terms: the comma-separated line under "## Trigger terms".
    terms: list[str] = []
    tmatch = re.search(r"##\s*Trigger terms\s*\n(.+)", text)
    if tmatch:
        terms = [t.strip() for t in tmatch.group(1).split(",") if t.strip()]

    # Red flags: every "- RF-...: ..." bullet.
    red_flags = [f"{rid}: {body.strip()}" for rid, body in re.findall(r"-\s*(RF-[\w-]+):\s*(.+)", text)]

    return Advisory(
        advisory_id=_parse_meta(text, "Advisory ID") or "UNKNOWN",
        title=title,
        source=_parse_meta(text, "Source"),
        sar_key_term=_parse_meta(text, "SAR key term"),
        sar_fields=_parse_meta(text, "Associated SAR fields"),
        trigger_terms=terms,
        red_flags=red_flags,
    )


def _term_pattern(term: str) -> re.Pattern:
    # Word-boundary match for alphanumeric terms; substring for the rest.
    escaped = re.escape(term)
    if term[:1].isalnum() and term[-1:].isalnum():
        escaped = rf"\b{escaped}\b"
    return re.compile(escaped, re.IGNORECASE)


def match_advisory(
    documents: Iterable[tuple[str, Provenance]],
    advisory: Optional[Advisory] = None,
) -> Optional[AdvisoryMatch]:
    """Scan (text, provenance) documents for advisory trigger terms.

    Returns an :class:`AdvisoryMatch` if any trigger term is found, else ``None``.
    """
    adv = advisory or load_advisory()
    patterns = [(t, _term_pattern(t)) for t in adv.trigger_terms]

    matched: dict[str, None] = {}  # preserve order, dedupe
    provenance: list[Provenance] = []
    for text, prov in documents:
        if not text:
            continue
        hit_here = False
        for term, pat in patterns:
            if pat.search(text):
                matched.setdefault(term, None)
                hit_here = True
        if hit_here:
            provenance.append(prov)

    if not matched:
        return None

    return AdvisoryMatch(
        advisory_id=adv.advisory_id,
        title=adv.title,
        sar_key_term=adv.sar_key_term,
        sar_fields=adv.sar_fields,
        matched_terms=list(matched.keys()),
        red_flags=adv.red_flags,
        provenance=provenance,
    )
