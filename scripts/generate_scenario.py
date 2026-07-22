#!/usr/bin/env python3
"""Generate the synthetic oil/sanctions-evasion scenario and print a summary.

    python scripts/generate_scenario.py [--seed 42] [--out data/synthetic]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `src/` importable when run from the repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from okojo.config import SEED, SYNTHETIC_DIR  # noqa: E402
from okojo.scenario import generate_scenario  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Generate Okojo's synthetic scenario.")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", type=Path, default=SYNTHETIC_DIR)
    args = p.parse_args()

    summary = generate_scenario(out_dir=args.out, seed=args.seed)
    print(json.dumps(summary, indent=2))
    print(f"\nWrote synthetic scenario to: {summary['output_dir']}")


if __name__ == "__main__":
    main()
