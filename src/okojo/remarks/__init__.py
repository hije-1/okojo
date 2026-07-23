"""Remark/Tell Miner — surfaces attribution tells in free-text (Component 4)."""

from __future__ import annotations

from .miner import RemarkTell, mine_remarks
from .screening import SCREEN_THRESHOLD, AliasMatch, screen_aliases

__all__ = ["RemarkTell", "mine_remarks", "AliasMatch", "screen_aliases", "SCREEN_THRESHOLD"]
