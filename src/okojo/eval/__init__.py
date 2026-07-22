"""Evaluation harness — set-based precision / recall / F1 (Component: eval).

Every Okojo capability ships with an eval scored against
``data/synthetic/ground_truth.json``. The helpers here operate on sets of
predicted vs. gold items (uids, tx_ids, addresses, edges…), so the same math
serves the network, tell-miner, and risk-scorer evals.
"""

from __future__ import annotations

from .metrics import Score, f1, precision, recall, score

__all__ = ["Score", "precision", "recall", "f1", "score"]
