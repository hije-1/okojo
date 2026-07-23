"""Shared entity backbone — one canonical entity view across components."""

from __future__ import annotations

from .backbone import (
    STOP_TOKENS,
    Entity,
    EntityAddress,
    EntityBackbone,
    WatchlistEntity,
    build_backbone,
    name_tokens,
)

__all__ = [
    "STOP_TOKENS",
    "Entity",
    "EntityAddress",
    "EntityBackbone",
    "WatchlistEntity",
    "build_backbone",
    "name_tokens",
]
