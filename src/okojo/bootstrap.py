"""Boot-time synthetic-data bootstrap.

The repo commits only the deterministic generator, never ``data/synthetic/``
(it regenerates byte-identically from a fixed seed, so shipping it would be
redundant). On a fresh clone — most importantly a cloud deploy that starts from
a bare checkout — the dataset is therefore absent, and the first thing a boot
needs is to regenerate it in-process before any connector tries to read it.

This module is that hook, and nothing more. Its guarantees:

- it runs the generator **only** when the dataset is missing or incomplete;
- it **never overwrites** a dataset that is already present — every existing
  local and CI path already has data on disk, so the hook is a no-op there
  (byte-identical by construction);
- it is **deterministic**: the seeded generator reproduces exactly the committed
  bytes, so a boot-regenerated dataset equals a committed-generator one.

The default hook is cached to run at most once per process.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Optional

from .config import SEED, SYNTHETIC_DIR
from .connectors import TABLES
from .scenario import generate_scenario


def scenario_dataset_present(data_dir: Path) -> bool:
    """True iff every generator CSV exists in ``data_dir``.

    This is the same completeness definition the DuckDB ``Store`` loads against,
    so "present" here means exactly "loadable there" — a partial directory
    counts as missing and triggers a clean regeneration.
    """
    return all((Path(data_dir) / fname).exists() for fname in TABLES.values())


def provision_scenario_dataset(
    data_dir: Optional[Path] = None, *, seed: int = SEED
) -> bool:
    """Generate the synthetic scenario dataset iff it is missing/incomplete.

    Returns ``True`` if it regenerated, ``False`` if a complete dataset was
    already present (and left byte-untouched). Non-destructive by construction:
    it never writes when the data is already there, so it can never clobber a
    committed or previously generated dataset.
    """
    target = Path(data_dir) if data_dir is not None else SYNTHETIC_DIR
    if scenario_dataset_present(target):
        return False
    generate_scenario(out_dir=target, seed=seed)
    return True


@functools.lru_cache(maxsize=1)
def ensure_default_scenario_dataset() -> bool:
    """The process-level boot hook: ensure the default dataset once.

    Wraps :func:`provision_scenario_dataset` for the real ``SYNTHETIC_DIR`` and
    memoizes the result, so repeated boots within one process (e.g. Streamlit
    reruns) check the filesystem at most once.
    """
    return provision_scenario_dataset(SYNTHETIC_DIR)
