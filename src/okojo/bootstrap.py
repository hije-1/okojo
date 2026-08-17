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
  regenerated into a temporary sibling directory and moved into place only once
  complete. This is NOT a per-file merge — any surviving generated file in an
  incomplete directory is replaced, not preserved (the files are reproducible
  synthetic outputs, so there is nothing to preserve). A **failed** regeneration
  leaves the existing files intact;
- the swap is **staged, not atomic**. Replacing an existing directory takes two
  sequential renames — the old directory aside to a backup name, then the staged
  one into place — and each rename is atomic on its own, but the pair is not an
  atomic directory exchange: between them the target path does not exist. A
  reader arriving in that window sees no dataset, and a process killed there
  leaves the displaced directory under a backup name — normally the incomplete
  set that triggered the regeneration, but a **complete** one if a concurrent
  boot's swap landed in between. Rather than pretend the window away, the hook
  **recovers**: it restores an orphaned backup at boot (see
  :func:`provision_scenario_dataset`). The data is synthetic and reproducible,
  so recovery — not interprocess locking — is the proportionate answer here;
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


def _backup_prefix(target: Path) -> str:
    """The name prefix the swap parks a displaced dataset under.

    One definition, two consumers — the swap that creates the backup and the
    recovery that finds it — so the two can never disagree about the name.
    """
    return f".{target.name}.old-"


def _recover_interrupted_swap(target: Path) -> None:
    """Restore a dataset left under a backup name by an interrupted swap.

    The swap window (see the module docstring) is between the two renames, where
    the target path does not exist and the data lives only under a backup name.
    A process killed there is repaired here, on the next boot, before the
    ordinary missing/incomplete logic runs.

    Restores only from a backup that is **itself complete**: an incomplete backup
    is discarded, never installed, so recovery can never leave a worse dataset
    than plain regeneration would produce. This is the distinction that decides
    the two cases — the swap only ever displaces a directory it found incomplete,
    so a single interrupted boot leaves an incomplete backup with nothing worth
    restoring, while a backup that IS complete means a concurrent boot's swap
    landed in between and its finished dataset is the thing this window put at
    risk. Candidates are taken in sorted order so the outcome is deterministic
    when more than one exists.

    Orphaned *staging* directories are deliberately left alone — a concurrent
    boot may still own one.
    """
    if scenario_dataset_present(target):
        return  # nothing to recover: the dataset on disk is already complete
    prefix = _backup_prefix(target)
    for backup in sorted(target.parent.glob(f"{prefix}*")):
        if not backup.is_dir():
            continue
        if not scenario_dataset_present(backup):
            shutil.rmtree(backup, ignore_errors=True)
            continue
        # An incomplete target is reproducible synthetic output, so the complete
        # backup is unambiguously the better of the two — drop it and restore.
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        os.replace(backup, target)
        return


def provision_scenario_dataset(
    data_dir: Optional[Path] = None, *, seed: int = SEED
) -> bool:
    """Generate the synthetic scenario dataset iff it is missing/incomplete.

    Returns ``True`` if it regenerated, ``False`` if a complete dataset was
    already present or was recovered intact (and left byte-untouched either way).

    Regeneration is all-or-nothing and honest about it:

    - a dataset left under a backup name by an interrupted swap is **restored
      first**, so a killed process is repaired rather than regenerated around;
    - a complete dataset is left untouched (a no-op ``False``);
    - an incomplete dataset is regenerated into a temporary sibling directory and
      moved into place only once complete. This **replaces the directory
      wholesale** — a surviving generated file is not preserved (the outputs are
      reproducible);
    - if generation fails, the existing directory is left exactly as it was;
    - replacing an existing directory takes two sequential renames, and the
      target path does not exist between them. That window is real; an
      in-process failure is rolled back, and a killed process is recovered by
      the next call.
    """
    target = Path(data_dir) if data_dir is not None else SYNTHETIC_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    _recover_interrupted_swap(target)
    if scenario_dataset_present(target):
        return False

    # Generate into a temp sibling on the SAME filesystem, so moving it into place
    # is a rename rather than a copy. The dataset is only ever the pre-existing
    # (possibly partial) set or the complete new one — never a written mixture.
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-",
                                    dir=target.parent))
    try:
        generate_scenario(out_dir=staging, seed=seed)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise  # generation failed: the original directory is untouched

    # Stage the swap: move any existing directory aside, move the complete staged
    # dataset into place, then drop the old one. If either rename fails in-process
    # the original is restored; if the process dies between them the backup name
    # is what _recover_interrupted_swap finds on the next boot.
    backup = target.with_name(f"{_backup_prefix(target)}{staging.name}")
    moved_aside = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_aside = True
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
