"""Regulatory Advisory Matcher (Phase 3 — hybrid retrieval + corroboration).

Loads an ingested FinCEN advisory (the committed key-terms extract) and matches
it against a case using three independent signals:

1. **Keyword/regex** — the advisory's published trigger terms over case text.
2. **Semantic** — cosine similarity of case text against each numbered red-flag
   indicator (``RF-*``), so a paraphrase that shares no trigger word still maps
   to the specific indicator it resembles. See :mod:`okojo.advisory.retrieval`.
3. **Structured** — advisory-named attributes (jurisdictions, watchlist linkage,
   on-chain sanctioned exposure) checked against the shared
   :class:`~okojo.entity.EntityBackbone` and the case's screening/exposure facts.

**Corroboration rule.** A keyword/semantic hit alone is a *topical* signal and
noisy on its own. When structured case evidence is available (always, in the
running pipeline) a match is surfaced only if a primary hit is **corroborated**
by >=1 structured corroborator — the gate that removes topical-but-innocent text.
Without structured context (isolated calls/unit tests) the matcher degrades to
keyword surfacing, never fabricating a corroborator it does not have.

Every asserted fact carries provenance (the grounding contract). This module
prepares evidence for a human reviewer; it does not screen, advise, or file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel

from ..provenance import Provenance
from .embeddings import DEFAULT_MODEL, LexicalFallbackEmbedder
from .retrieval import CosineRetriever

_CORPUS_DIR = Path(__file__).parent / "corpus"
_DEFAULT_CORPUS = _CORPUS_DIR / "iran_oil_keyterms.md"

# Semantic cosine threshold. Calibrated on the crafted advisory gold set so that
# paraphrased red-flag hits clear it while off-topic decoys sit below — the same
# "true hits cluster high, decoys low, pick the gap" method as SCREEN_THRESHOLD.
# The value is embedder-dependent (the lexical fallback's cosines are compressed
# vs. a neural model's); it is recorded together with the active embedder name in
# docs/advisory-methodology.md, and the corroboration gate is the primary
# false-positive control regardless of where this dial sits.
SEMANTIC_THRESHOLD = 0.22

# How many red-flag indicators a single case document may match semantically.
SEMANTIC_TOP_K = 3

# Version of the retrieval methodology (the hybrid signals + corroboration gate +
# semantic threshold). Bumped on any change to those; stamped into the audit trail
# and mirrored (+ regression-tested) by docs/advisory-methodology.md, exactly as the
# scorer's SCORING_VERSION mirrors docs/scoring-methodology.md.
RETRIEVAL_VERSION = "1.0.0"


def retrieval_config() -> dict:
    """The versioned advisory-retrieval configuration — the single source of truth.

    Stamped into the tamper-evident audit trail for reproducibility and regression-
    tested against docs/advisory-methodology.md so the doc and code can never
    silently drift. Deliberately **static policy** (no runtime-active embedder, no
    advisory list): the active embedder is recorded separately by the orchestrator,
    and the corpus is data, not policy — so this block is identical whether or not
    the local sentence-transformers backend is installed.
    """
    return {
        "version": RETRIEVAL_VERSION,
        "embedder": DEFAULT_MODEL,
        "embedder_fallback": LexicalFallbackEmbedder.name,
        "semantic_threshold": SEMANTIC_THRESHOLD,
        "top_k": SEMANTIC_TOP_K,
        "corroboration_rule": "primary_hit(keyword OR semantic) AND >=1 structured corroborator",
        "jurisdictions_source": "shared EntityBackbone (residence + nationality + KYC-issuing country)",
    }


class RedFlag(BaseModel):
    rf_id: str
    text: str


class Advisory(BaseModel):
    advisory_id: str
    title: str
    source: str
    sar_key_term: str
    sar_fields: str
    trigger_terms: list[str]
    red_flags: list[str]                     # "RF-X: body" (back-compat; UI + SAR)
    red_flag_items: list[RedFlag] = []       # structured, for semantic retrieval
    jurisdictions: list[str] = []            # ISO codes the advisory implicates


class SemanticIndicator(BaseModel):
    """A numbered red-flag indicator matched semantically to case text."""

    rf_id: str
    text: str
    score: float
    provenance: Provenance


class JurisdictionSignal(BaseModel):
    code: str
    provenance: Provenance


class Corroborator(BaseModel):
    """A structured case fact that corroborates a topical (keyword/semantic) hit."""

    kind: str          # "jurisdiction" | "watchlist" | "sanctioned_exposure"
    detail: str
    provenance: Provenance


class StructuredContext(BaseModel):
    """Structured case evidence the corroboration pass checks against."""

    jurisdictions: list[JurisdictionSignal] = []
    watchlist_hit: Optional[Provenance] = None
    sanctioned_exposure: Optional[Provenance] = None


class AdvisoryMatch(BaseModel):
    advisory_id: str
    title: str
    sar_key_term: str
    sar_fields: str
    matched_terms: list[str]                 # keyword trigger terms hit (back-compat)
    red_flags: list[str]
    provenance: list[Provenance]
    # Phase 3 hybrid detail:
    signals: list[str] = []                  # which of keyword/semantic/structured fired
    semantic_indicators: list[SemanticIndicator] = []
    corroborators: list[Corroborator] = []
    corroborated: bool = False


# --------------------------------------------------------------------------- #
# Corpus loading / parsing
# --------------------------------------------------------------------------- #
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
    rf_pairs = re.findall(r"-\s*(RF-[\w-]+):\s*(.+)", text)
    red_flags = [f"{rid}: {body.strip()}" for rid, body in rf_pairs]
    red_flag_items = [RedFlag(rf_id=rid, text=body.strip()) for rid, body in rf_pairs]

    # Jurisdictions: comma-separated ISO codes on the "- **Jurisdictions:** ..." line.
    juris_raw = _parse_meta(text, "Jurisdictions")
    jurisdictions = [j.strip().upper() for j in juris_raw.split(",") if j.strip()]

    return Advisory(
        advisory_id=_parse_meta(text, "Advisory ID") or "UNKNOWN",
        title=title,
        source=_parse_meta(text, "Source"),
        sar_key_term=_parse_meta(text, "SAR key term"),
        sar_fields=_parse_meta(text, "Associated SAR fields"),
        trigger_terms=terms,
        red_flags=red_flags,
        red_flag_items=red_flag_items,
        jurisdictions=jurisdictions,
    )


def load_advisories(corpus_dir: Optional[Path] = None) -> list[Advisory]:
    """Load every advisory extract in the corpus directory (Phase 3 multi-advisory).

    Sorted glob so the corpus order is deterministic. ``load_advisory`` (single,
    default Iran path) is kept for callers that want just the one advisory.
    """
    corpus_dir = Path(corpus_dir) if corpus_dir else _CORPUS_DIR
    return [load_advisory(p) for p in sorted(corpus_dir.glob("*.md"))]


# --------------------------------------------------------------------------- #
# Retrieval / structured helpers
# --------------------------------------------------------------------------- #
def build_advisory_retriever(advisory: Advisory, embedder=None) -> CosineRetriever:
    """Index the advisory's numbered red-flag indicators for semantic retrieval."""
    items = [(rf.text, {"rf_id": rf.rf_id, "text": rf.text}) for rf in advisory.red_flag_items]
    return CosineRetriever(embedder).index(items)


def build_structured_context(
    backbone,
    *,
    watchlist_provenance: Optional[Provenance] = None,
    exposure_provenance: Optional[Provenance] = None,
) -> StructuredContext:
    """Assemble the case's raw structured facts (advisory-agnostic).

    Carries every jurisdiction the case's entities sit in, plus optional
    watchlist-linkage and on-chain-exposure pointers. The advisory-specific
    relevance test (which jurisdictions the advisory actually names) is applied
    later by the matcher, so one context is reusable across advisories.
    """
    juris: list[JurisdictionSignal] = []
    seen: set[str] = set()
    for e in backbone.entities:
        for code in e.jurisdictions:
            if code not in seen:
                seen.add(code)
                juris.append(JurisdictionSignal(code=code, provenance=e.provenance))
    return StructuredContext(
        jurisdictions=juris,
        watchlist_hit=watchlist_provenance,
        sanctioned_exposure=exposure_provenance,
    )


def _corroborators_for(advisory: Advisory, structured: StructuredContext) -> list[Corroborator]:
    """Structured corroborators: a case fact that the advisory actually implicates."""
    out: list[Corroborator] = []
    adv_juris = set(advisory.jurisdictions)
    for j in structured.jurisdictions:
        if j.code not in adv_juris:
            continue  # a jurisdiction the advisory does not name is not a corroborator
        out.append(Corroborator(
            kind="jurisdiction",
            detail=f"a case entity is in {j.code}, a jurisdiction the advisory names",
            provenance=j.provenance,
        ))
    if structured.watchlist_hit is not None:
        out.append(Corroborator(
            kind="watchlist",
            detail="an account name resembles a synthetic watchlist alias",
            provenance=structured.watchlist_hit,
        ))
    if structured.sanctioned_exposure is not None:
        out.append(Corroborator(
            kind="sanctioned_exposure",
            detail="the case has on-chain exposure to the synthetic sanctioned set",
            provenance=structured.sanctioned_exposure,
        ))
    return out


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def _term_pattern(term: str) -> re.Pattern:
    # Word-boundary match for alphanumeric terms; substring for the rest.
    escaped = re.escape(term)
    if term[:1].isalnum() and term[-1:].isalnum():
        escaped = rf"\b{escaped}\b"
    return re.compile(escaped, re.IGNORECASE)


def match_advisory(
    documents: Iterable[tuple[str, Provenance]],
    advisory: Optional[Advisory] = None,
    *,
    retriever: Optional[CosineRetriever] = None,
    structured: Optional[StructuredContext] = None,
    semantic_threshold: float = SEMANTIC_THRESHOLD,
    require_corroboration: bool = True,
) -> Optional[AdvisoryMatch]:
    """Hybrid match of an advisory against case documents.

    Combines a keyword pass, an optional semantic pass (when ``retriever`` is
    supplied), and an optional structured-corroboration pass (when ``structured``
    is supplied). When structured context is available and ``require_corroboration``
    is set, a topical hit is surfaced only if >=1 structured corroborator fires.
    Returns the :class:`AdvisoryMatch`, or ``None`` if nothing qualifies.
    """
    adv = advisory or load_advisory()
    patterns = [(t, _term_pattern(t)) for t in adv.trigger_terms]
    docs = [(text, prov) for text, prov in documents if text]

    # -- keyword pass ------------------------------------------------------- #
    keyword_terms: dict[str, None] = {}   # ordered, deduped
    provenance: list[Provenance] = []
    seen_prov: set[Provenance] = set()

    def _add_prov(p: Optional[Provenance]) -> None:
        if p is not None and p not in seen_prov:
            seen_prov.add(p)
            provenance.append(p)

    for text, prov in docs:
        hit_here = False
        for term, pat in patterns:
            if pat.search(text):
                keyword_terms.setdefault(term, None)
                hit_here = True
        if hit_here:
            _add_prov(prov)

    # -- semantic pass ------------------------------------------------------ #
    semantic: dict[str, SemanticIndicator] = {}   # rf_id -> best indicator
    if retriever is not None:
        for text, prov in docs:
            for item in retriever.query(text, top_k=SEMANTIC_TOP_K, min_score=semantic_threshold):
                rf_id = item.metadata.get("rf_id", "")
                cur = semantic.get(rf_id)
                if cur is None or item.score > cur.score:
                    semantic[rf_id] = SemanticIndicator(
                        rf_id=rf_id,
                        text=item.metadata.get("text", item.text),
                        score=item.score,
                        provenance=prov,
                    )
        for ind in semantic.values():
            _add_prov(ind.provenance)

    # -- structured corroboration ------------------------------------------ #
    corroborators = _corroborators_for(adv, structured) if structured is not None else []

    primary_hit = bool(keyword_terms) or bool(semantic)
    corroborated = bool(corroborators)

    if not primary_hit:
        return None
    # Enforce the gate only when structured evidence was actually supplied.
    if structured is not None and require_corroboration and not corroborated:
        return None

    for c in corroborators:
        _add_prov(c.provenance)

    signals: list[str] = []
    if keyword_terms:
        signals.append("keyword")
    if semantic:
        signals.append("semantic")
    if corroborators:
        signals.append("structured")

    # Semantic indicators sorted by score desc (stable) for a deterministic view.
    semantic_sorted = sorted(semantic.values(), key=lambda s: (-s.score, s.rf_id))

    return AdvisoryMatch(
        advisory_id=adv.advisory_id,
        title=adv.title,
        sar_key_term=adv.sar_key_term,
        sar_fields=adv.sar_fields,
        matched_terms=list(keyword_terms.keys()),
        red_flags=adv.red_flags,
        provenance=provenance,
        signals=signals,
        semantic_indicators=semantic_sorted,
        corroborators=corroborators,
        corroborated=corroborated,
    )


def _match_rank_key(m: AdvisoryMatch) -> tuple:
    """Deterministic best-first ordering across advisories.

    In priority order: more independent signal types win; then more published
    trigger terms (keyword specificity); then more structured corroborators — this
    is what discriminates the *right* advisory from a merely topical one when two
    advisories both fire semantically, since a jurisdiction corroborator is
    advisory-specific while the semantic pass is noisier; then more/stronger
    semantic indicators; then the advisory id (stable tiebreak).
    """
    best_semantic = max((s.score for s in m.semantic_indicators), default=0.0)
    return (
        -len(m.signals),
        -len(m.matched_terms),
        -len(m.corroborators),
        -len(m.semantic_indicators),
        -best_semantic,
        m.advisory_id,
    )


def match_advisories(
    documents: Iterable[tuple[str, Provenance]],
    advisories: Iterable[Advisory],
    *,
    retrievers: Optional[dict[str, CosineRetriever]] = None,
    structured: Optional[StructuredContext] = None,
    semantic_threshold: float = SEMANTIC_THRESHOLD,
    require_corroboration: bool = True,
) -> list[AdvisoryMatch]:
    """Match a case against several advisories; return the survivors, best first.

    Each advisory is matched independently by :func:`match_advisory` (its own
    retriever, keyed by ``advisory_id`` in ``retrievers``), so the corroboration
    gate discriminates the *right* advisory from a merely topical one. Results are
    ranked deterministically (see :func:`_match_rank_key`); the caller typically
    takes ``[0]`` as the single best match. Returns ``[]`` if nothing qualifies.
    """
    docs = list(documents)  # materialise: reused across every advisory
    matches: list[AdvisoryMatch] = []
    for adv in advisories:
        retriever = retrievers.get(adv.advisory_id) if retrievers else None
        m = match_advisory(
            docs,
            adv,
            retriever=retriever,
            structured=structured,
            semantic_threshold=semantic_threshold,
            require_corroboration=require_corroboration,
        )
        if m is not None:
            matches.append(m)
    matches.sort(key=_match_rank_key)
    return matches
