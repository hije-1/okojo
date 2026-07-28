"""Variant-aware name expansion and screening.

Expand a designated name into its published-romanization variant space, then
fuzzy-match each variant against customer-typed account names. Each hit records
WHICH rule path fired (the equivalence classes that bridged the gap) and the
score — the evidence for HOW the name resolved, so a reviewer sees the
transliteration reasoning, never a bare "match".

Deterministic and RNG-free: variant enumeration is an ordered Cartesian product
over the ordered equivalence classes; ties in scoring break toward the
lexicographically smallest variant. The layer only claims a match when a
transliteration rule actually fired — a name that reaches threshold with no rule
applied is, by definition, a DIRECT screen hit (surfaced by the existing
``match_designated_name``), not a variant one.
"""

from __future__ import annotations

import itertools

from pydantic import BaseModel
from rapidfuzz import fuzz

from ..connectors import Connectors
from ..provenance import Provenance
from . import VARIANT_MATCH_THRESHOLD, _equivalence_classes


def _norm_token(tok: str) -> str:
    """Lowercase, strip surrounding punctuation/whitespace — the comparison form."""
    return tok.lower().strip().strip("-").strip("'").strip()


def _tokenize(name: str) -> list[str]:
    """Split a name into comparison tokens, splitting a hyphenated article
    (``Al-Sayigh`` -> ``al`` ``sayigh``) so the article class can fire."""
    return [_norm_token(t) for t in name.replace("-", " ").split() if _norm_token(t)]


def expand_name_variants(name: str) -> list[tuple[str, tuple[str, ...]]]:
    """Expand ``name`` into (variant, fired_rule_ids) pairs.

    ``fired_rule_ids`` is the ordered tuple of equivalence-class ids whose form
    was substituted for the ORIGINAL token to reach this variant (empty for the
    identity variant). Deterministic order; the identity variant (no rule fired)
    is always present and first.
    """
    classes = _equivalence_classes()
    tokens = _tokenize(name)

    # Per-token options: (form, rule_id_or_None). The original token first
    # (rule None), then each class form the token belongs to, in class order.
    per_token: list[list[tuple[str, str | None]]] = []
    for tok in tokens:
        opts: list[tuple[str, str | None]] = [(tok, None)]
        for cls in classes:
            if tok in cls["forms"]:
                for form in cls["forms"]:
                    if form != tok:
                        opts.append((form, cls["id"]))
        per_token.append(opts)

    seen: dict[str, tuple[str, ...]] = {}
    for combo in itertools.product(*per_token):
        variant = " ".join(form for form, _ in combo)
        fired = tuple(rid for (form, rid), tok in zip(combo, tokens)
                      if rid is not None and form != tok)
        # Keep the first (smallest fired-set) path to a given variant string.
        if variant not in seen or len(fired) < len(seen[variant]):
            seen[variant] = fired
    # Deterministic: identity variant first, then by variant string.
    identity = " ".join(tokens)
    ordered = sorted(seen.items(), key=lambda kv: (kv[0] != identity, kv[0]))
    return [(v, f) for v, f in ordered]


class VariantNameMatch(BaseModel):
    """A customer account whose name matches a designated name via a documented
    romanization equivalence path (that the direct screen misses)."""

    uid: int
    entity_name: str
    designated_name: str
    matched_variant: str          # the romanization form that scored the hit
    rule_path: list[str]          # equivalence-class ids that fired, in order
    rule_families: list[str]      # the families those classes belong to
    score: float
    provenance: list[Provenance]


def screen_name_variants(
    conn: Connectors,
    designated_name: str,
    exclude_uids: set[int] | None = None,
    threshold: int = VARIANT_MATCH_THRESHOLD,
) -> list[VariantNameMatch]:
    """Screen every account name against the designated name's variant space.

    Returns only matches the direct screen would MISS: an account in
    ``exclude_uids`` (already a direct hit) is skipped, and a match is recorded
    only when a transliteration rule actually fired (``rule_path`` non-empty).
    Each hit is grounded in the account row it screens; ordered by uid.
    """
    exclude = exclude_uids or set()
    variants = expand_name_variants(designated_name)
    family_of = {c["id"]: c["family"] for c in _equivalence_classes()}

    hits: list[VariantNameMatch] = []
    for acct in conn.all_accounts():
        uid = int(acct["uid"])
        if uid in exclude:
            continue
        cust = " ".join(_tokenize(str(acct["entity_name"])))
        best_score = -1.0
        best_variant = ""
        best_fired: tuple[str, ...] = ()
        for variant, fired in variants:
            if not fired:
                continue  # identity variant is the direct screen's job
            s = fuzz.WRatio(variant, cust)
            if s > best_score or (s == best_score and variant < best_variant):
                best_score, best_variant, best_fired = s, variant, fired
        if best_score >= threshold and best_fired:
            hits.append(VariantNameMatch(
                uid=uid,
                entity_name=str(acct["entity_name"]),
                designated_name=designated_name,
                matched_variant=best_variant,
                rule_path=list(best_fired),
                rule_families=sorted({family_of[r] for r in best_fired}),
                score=round(float(best_score), 1),
                provenance=[acct.provenance],
            ))
    return sorted(hits, key=lambda h: h.uid)
