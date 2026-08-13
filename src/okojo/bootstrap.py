"""Boot-time synthetic-data bootstrap.

The repo commits only the deterministic generator, never ``data/synthetic/``
(it regenerates byte-identically from a fixed seed, so shipping it would be
redundant). On a fresh clone — most importantly a cloud deploy that starts from
a bare checkout — the dataset is therefore absent, and the first thing a boot
needs is to regenerate it in-process before any connector tries to read it.

This module is that hook, and nothing more. Its guarantees:

- it runs the generator **only** when the dataset is missing or incomplete;
- a **complete** dataset is left byte-untouched — every existing local and CI
  path already has data on disk, so the hook is a no-op there;
- an **incomplete** dataset is replaced **wholesale**: the whole synthetic set is
  regenerated and the complete result is swapped in atomically. This is NOT a
  per-file merge — any surviving generated file in an incomplete directory is
  replaced, not preserved (the files are reproducible synthetic outputs, so there
  is nothing to preserve). Regeneration happens in a temporary sibling directory
  and is swapped in only once complete, so a boot never observes a half-written
  dataset, and a **failed** regeneration leaves the existing files intact;
- it is **deterministic**: the seeded generator reproduces exactly the committed
  bytes, so a boot-regenerated dataset equals a committed-generator one.

The default hook is cached to run at most once per process.
"""

from __future__ import annotations

import functools
import os
import shutil
import tempfile
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
    already present (and left byte-untouched).

    Regeneration is all-or-nothing and honest about it:

    - a complete dataset is left untouched (a no-op ``False``);
    - an incomplete dataset is regenerated into a temporary sibling directory and
      swapped in atomically once complete, so a concurrent boot never sees a
      half-written dataset. This **replaces the directory wholesale** — a
      surviving generated file is not preserved (the outputs are reproducible);
    - if generation fails, the existing directory is left exactly as it was.
    """
    target = Path(data_dir) if data_dir is not None else SYNTHETIC_DIR
    if scenario_dataset_present(target):
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    # Generate into a temp sibling on the SAME filesystem, so the final move is an
    # atomic rename. The dataset is only ever the pre-existing (possibly partial)
    # set or the complete new one — never a partially-written mixture.
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-",
                                    dir=target.parent))
    try:
        generate_scenario(out_dir=staging, seed=seed)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise  # generation failed: the original directory is untouched

    # Atomic swap: move any existing directory aside, move the complete staged
    # dataset into place, then drop the old one. If the second rename fails, the
    # original is restored so a failure never leaves the target missing.
    backup = target.with_name(f".{target.name}.old-{staging.name}")
    moved_aside = False
    if target.exists():
        os.replace(target, backup)
        moved_aside = True
    try:
        os.replace(staging, target)
    except BaseException:
        if moved_aside:
            os.replace(backup, target)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if moved_aside:
        shutil.rmtree(backup, ignore_errors=True)
    return True


@functools.lru_cache(maxsize=1)
def ensure_default_scenario_dataset() -> bool:
    """The process-level boot hook: ensure the default dataset once.

    Wraps :func:`provision_scenario_dataset` for the real ``SYNTHETIC_DIR`` and
    memoizes the result, so repeated boots within one process (e.g. Streamlit
    reruns) check the filesystem at most once.
    """
    return provision_scenario_dataset(SYNTHETIC_DIR)
