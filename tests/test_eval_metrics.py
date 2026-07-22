"""Unit tests for the set-based precision/recall/F1 eval helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from okojo.eval import f1, precision, recall, score  # noqa: E402


def test_perfect_match():
    s = score({1, 2, 3}, {1, 2, 3})
    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0
    assert (s.tp, s.fp, s.fn) == (3, 0, 0)


def test_partial_match():
    # predicted {1,2,4}; gold {1,2,3}: tp=2, fp=1 (4), fn=1 (3)
    s = score({1, 2, 4}, {1, 2, 3})
    assert (s.tp, s.fp, s.fn) == (2, 1, 1)
    assert s.precision == 2 / 3
    assert s.recall == 2 / 3
    assert abs(s.f1 - 2 / 3) < 1e-12


def test_no_predictions_is_vacuously_precise_but_zero_recall():
    s = score(set(), {1, 2, 3})
    assert s.precision == 1.0  # asserted nothing false
    assert s.recall == 0.0
    assert s.f1 == 0.0  # honest headline


def test_nothing_to_find():
    s = score(set(), set())
    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0


def test_all_false_positives():
    s = score({9, 10}, set())
    assert s.precision == 0.0  # every prediction is wrong
    assert s.recall == 1.0  # nothing to find
    assert s.f1 == 0.0


def test_free_functions_agree_with_score():
    pred, gold = {1, 2, 4, 5}, {1, 2, 3}
    s = score(pred, gold)
    assert precision(pred, gold) == s.precision
    assert recall(pred, gold) == s.recall
    assert f1(pred, gold) == s.f1


def test_accepts_any_hashable_and_iterable():
    # lists with duplicates, string ids — deduped internally
    s = score(["SIMTX1", "SIMTX1", "SIMTX2"], ["SIMTX2", "SIMTX3"])
    assert (s.tp, s.fp, s.fn) == (1, 1, 1)
