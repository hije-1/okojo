"""Set-based precision / recall / F1 for capability evaluation.

All Okojo capabilities are scored by comparing a *predicted* set of items
against a *gold* set drawn from ``ground_truth.json``. Keeping the metric math
in one place means the network, tell-miner, and risk-scorer evals report the
same, comparable numbers.

Conventions for the degenerate cases (documented so scorecards are readable):
  * ``tp = |pred ∩ gold|``, ``fp = |pred − gold|``, ``fn = |gold − pred|``.
  * **No predictions** (``tp + fp == 0``): ``precision = 1.0`` — vacuously, the
    model asserted nothing false.
  * **Nothing to find** (``tp + fn == 0``): ``recall = 1.0`` — vacuously, every
    gold item was recalled.
  * ``f1 = 0.0`` whenever ``precision + recall == 0``.
These make a predict-nothing model score ``precision=1.0, recall=0.0, f1=0.0``
— i.e. the F1 headline stays honest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Hashable, Iterable


@dataclass(frozen=True)
class Score:
    """A single precision/recall/F1 result with its confusion counts."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def as_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:  # compact, scorecard-friendly
        return (
            f"P={self.precision:.3f} R={self.recall:.3f} F1={self.f1:.3f} "
            f"(tp={self.tp} fp={self.fp} fn={self.fn})"
        )


def _confusion(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> tuple[int, int, int]:
    pred, want = set(predicted), set(gold)
    tp = len(pred & want)
    fp = len(pred - want)
    fn = len(want - pred)
    return tp, fp, fn


def precision(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> float:
    """Fraction of predicted items that are correct (1.0 if nothing predicted)."""
    tp, fp, _ = _confusion(predicted, gold)
    return tp / (tp + fp) if (tp + fp) else 1.0


def recall(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> float:
    """Fraction of gold items that were found (1.0 if there is nothing to find)."""
    tp, _, fn = _confusion(predicted, gold)
    return tp / (tp + fn) if (tp + fn) else 1.0


def f1(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> float:
    """Harmonic mean of precision and recall (0.0 if both are 0)."""
    p = precision(predicted, gold)
    r = recall(predicted, gold)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def score(predicted: Iterable[Hashable], gold: Iterable[Hashable]) -> Score:
    """Compute precision, recall, F1 and confusion counts in one pass."""
    pred, want = set(predicted), set(gold)
    tp = len(pred & want)
    fp = len(pred - want)
    fn = len(want - pred)
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return Score(precision=p, recall=r, f1=f, tp=tp, fp=fp, fn=fn)
