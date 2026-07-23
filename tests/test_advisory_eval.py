"""Advisory matcher evals on a crafted gold key. Ships as this capability's eval.

Two scorecards, both over the committed, hand-authored gold key
(``tests/data/advisory_gold.json``) so they are stable and never perturb the
seeded generator:

1. **Single-advisory FP-rate + gate ablation** (Iran advisory). Scoped to the
   cases whose ``expect_advisory`` is the Iran advisory or null. Demonstrates *why*
   the corroboration gate exists: with the gate on, topical-but-innocent oil text
   is suppressed; with it off, those cases reappear as false positives.
2. **Multi-advisory discrimination** (all four advisories). Runs
   :func:`match_advisories` and checks each case surfaces the *right* advisory (or
   none) — the wrong-advisory discrimination the corroboration gate + best-of
   ranking provide.

Both run on the deterministic lexical fallback embedder, so CI is hermetic and the
reported numbers reflect the fallback (not real neural embeddings) — see
``docs/advisory-methodology.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.advisory import (
    build_advisory_retriever,
    load_advisories,
    load_advisory,
    match_advisories,
    match_advisory,
)
from okojo.advisory.embeddings import LexicalFallbackEmbedder
from okojo.advisory.matcher import SEMANTIC_THRESHOLD, JurisdictionSignal, StructuredContext
from okojo.eval import score
from okojo.provenance import Provenance

_GOLD = json.loads((Path(__file__).parent / "data" / "advisory_gold.json").read_text(encoding="utf-8"))
_CASES = _GOLD["cases"]
_ADV = load_advisory()  # the Iran advisory (default corpus)

# The Iran advisory can only be scored against Iran-relevant cases: its own
# positives plus the null decoys. Cases planted for a *different* advisory belong
# to the multi-advisory discrimination scorecard, not this single-advisory one.
_IRAN_CASES = [c for c in _CASES if c.get("expect_advisory") in (None, _ADV.advisory_id)]


def _ctx(spec: dict) -> StructuredContext:
    juris = [
        JurisdictionSignal(code=c, provenance=Provenance(source="accounts", row_key=f"gold:{c}"))
        for c in spec.get("jurisdictions", [])
    ]
    wl = Provenance(source="sdn_list", row_key="gold:wl") if spec.get("watchlist") else None
    ex = Provenance(source="risk_scorer", row_key="gold:exposure") if spec.get("exposure") else None
    return StructuredContext(jurisdictions=juris, watchlist_hit=wl, sanctioned_exposure=ex)


# --------------------------------------------------------------------------- #
# 1) Single-advisory FP-rate + gate ablation (Iran advisory)
# --------------------------------------------------------------------------- #
def _run(require_corroboration: bool) -> set[str]:
    """Ids the Iran matcher surfaces across the Iran-scoped cases."""
    retriever = build_advisory_retriever(_ADV, LexicalFallbackEmbedder())
    matched: set[str] = set()
    for case in _IRAN_CASES:
        m = match_advisory(
            [(case["text"], Provenance(source="rfi", row_key=case["id"]))],
            _ADV,
            retriever=retriever,
            structured=_ctx(case["structured"]),
            require_corroboration=require_corroboration,
        )
        if m is not None:
            matched.add(case["id"])
    return matched


def _iran_positive() -> set[str]:
    return {c["id"] for c in _IRAN_CASES if c["expect_match"]}


def _iran_decoys() -> set[str]:
    return {c["id"] for c in _IRAN_CASES if not c["expect_match"]}


def test_advisory_fp_rate_scorecard(capsys):
    predicted = _run(require_corroboration=True)
    gold = _iran_positive()
    decoys = _iran_decoys()
    s = score(predicted, gold)
    fp_cases = predicted & decoys
    fp_rate = len(fp_cases) / len(decoys)

    with capsys.disabled():
        print("\nAdvisory matcher FP-rate scorecard (Iran advisory, crafted gold key):")
        print(f"  advisory_match: {s}")
        print(f"  false_positive_rate: {fp_rate:.3f} ({len(fp_cases)}/{len(decoys)} decoys)")
        print(f"  embedder: {LexicalFallbackEmbedder().name}  semantic_threshold: {SEMANTIC_THRESHOLD:.2f}")

    # recall = 1.0 on planted positives; zero false positives with the gate on.
    assert s.recall == 1.0, f"missed positives: {gold - predicted}"
    assert fp_rate == 0.0, f"false positives: {fp_cases}"
    assert s.precision == 1.0


def test_corroboration_gate_removes_false_positives():
    # Ablation: with the gate OFF, the topical-but-uncorroborated decoys reappear.
    with_gate = _run(require_corroboration=True) & _iran_decoys()
    without_gate = _run(require_corroboration=False) & _iran_decoys()
    assert len(without_gate) > len(with_gate), (
        "gate should remove at least one false positive vs. no gate"
    )
    assert len(with_gate) == 0
    # the specific topical decoys are what the gate catches
    assert {"D1-topical-uncorroborated", "D2-petrochemical-uncorroborated"}.issubset(without_gate)


# --------------------------------------------------------------------------- #
# 2) Multi-advisory discrimination (all four advisories)
# --------------------------------------------------------------------------- #
def _best_advisory_per_case() -> dict[str, str | None]:
    advisories = load_advisories()
    embedder = LexicalFallbackEmbedder()
    retrievers = {a.advisory_id: build_advisory_retriever(a, embedder) for a in advisories}
    out: dict[str, str | None] = {}
    for case in _CASES:
        matches = match_advisories(
            [(case["text"], Provenance(source="rfi", row_key=case["id"]))],
            advisories,
            retrievers=retrievers,
            structured=_ctx(case["structured"]),
        )
        out[case["id"]] = matches[0].advisory_id if matches else None
    return out


def test_advisory_discrimination(capsys):
    """Each case surfaces the RIGHT advisory (or none) among all four."""
    predicted = _best_advisory_per_case()
    expected = {c["id"]: c.get("expect_advisory") for c in _CASES}
    wrong = {cid: (predicted[cid], expected[cid]) for cid in expected if predicted[cid] != expected[cid]}
    correct = len(expected) - len(wrong)

    with capsys.disabled():
        print("\nAdvisory discrimination scorecard (4 advisories, crafted gold key):")
        print(f"  correct_advisory: {correct}/{len(expected)}")
        print(f"  embedder: {LexicalFallbackEmbedder().name}")
        for cid in sorted(expected):
            print(f"    {cid:34s} -> {predicted[cid]}  (expect {expected[cid]})")

    assert not wrong, f"mis-routed advisories: {wrong}"
