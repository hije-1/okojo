"""Global configuration and constants for Okojo.

Kept deliberately small and explicit. The scenario generator is fully
deterministic given SEED, so the same synthetic dataset regenerates every time
(no large data file needs to be committed — just the generator)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

# Reproducibility. Change the seed to draw a different synthetic world.
SEED: int = 42

# Deterministic "simulation clock" — we never use the real wall-clock date, so
# regenerated data is byte-for-byte stable.
SIM_START: date = date(2024, 1, 1)
SIM_END: date = date(2025, 12, 31)

# Where generated synthetic data is written (git-ignored).
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SYNTHETIC_DIR: Path = REPO_ROOT / "data" / "synthetic"

# Jurisdictions used to build a cross-border shell ring, mirroring the
# UAE/Türkiye/HK/NZ/CN spread seen in real oil/sanctions-evasion typologies.
RING_JURISDICTIONS: tuple[str, ...] = ("AE", "TR", "HK", "NZ", "CN")

# A sanctioned jurisdiction whose IP logins (interleaved with VPN) are a red
# flag. Fully synthetic IP ranges are generated in the RFC-5737 TEST-NET block.
SANCTIONED_JURISDICTION: str = "IR"
SANCTIONED_CITY: str = "Tehran"

# A structured "just-under" round number typical of structuring typologies.
STRUCTURED_AMOUNT: float = 1_999_999.0
