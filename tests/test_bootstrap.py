"""Boot-time synthetic-data bootstrap (Phase 10 B2).

Covers both branches of the boot hook — missing dataset regenerates and loads;
present dataset is left byte-untouched — and pins the determinism promise: a
boot-regenerated dataset equals a committed-generator one, byte-for-byte.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import okojo.bootstrap as bootstrap
from okojo.bootstrap import (
    ensure_default_scenario_dataset,
    provision_scenario_dataset,
    scenario_dataset_present,
)
from okojo.connectors import TABLES, Connectors
from okojo.scenario import generate_scenario


def _dir_hash(data_dir: Path) -> str:
    """Combined sha256 over every generator CSV, in TABLES order — a single
    fingerprint of the whole dataset's bytes."""
    h = hashlib.sha256()
    for fname in TABLES.values():
        h.update(fname.encode("utf-8"))
        h.update(b"\0")
        h.update((data_dir / fname).read_bytes())
    return h.hexdigest()


def test_missing_dataset_is_regenerated_and_loads(tmp_path):
    """Branch 1: an empty directory triggers regeneration, and the result is a
    complete, connector-loadable dataset."""
    assert not scenario_dataset_present(tmp_path)

    regenerated = provision_scenario_dataset(tmp_path)

    assert regenerated is True
    assert scenario_dataset_present(tmp_path)
    # The freshly regenerated dataset loads through the real connectors.
    conn = Connectors(data_dir=tmp_path)
    try:
        assert conn.all_accounts()  # non-empty
    finally:
        conn.close()


def test_present_dataset_is_left_untouched(tmp_path):
    """Branch 2: a complete dataset is never overwritten — same bytes before and
    after, and the hook reports it did nothing."""
    provision_scenario_dataset(tmp_path)
    before = _dir_hash(tmp_path)

    regenerated = provision_scenario_dataset(tmp_path)

    assert regenerated is False
    assert _dir_hash(tmp_path) == before


def test_partial_dataset_counts_as_missing(tmp_path):
    """A directory missing even one table is incomplete → regenerated, not
    treated as present (mirrors the Store's completeness definition)."""
    provision_scenario_dataset(tmp_path)
    # Remove one required CSV to simulate a partial/corrupt checkout.
    victim = tmp_path / next(iter(TABLES.values()))
    victim.unlink()
    assert not scenario_dataset_present(tmp_path)

    assert provision_scenario_dataset(tmp_path) is True
    assert scenario_dataset_present(tmp_path)


def test_incomplete_dataset_replaced_wholesale_not_preserved(tmp_path):
    """F-020 documented behavior: an incomplete dataset is regenerated WHOLESALE.
    A surviving file that was locally modified is REPLACED (not preserved), a
    missing file is restored, and the directory equals a fresh committed dataset
    afterward — no per-file preservation promise."""
    target = tmp_path / "synthetic"
    provision_scenario_dataset(target)  # seed a complete dataset
    names = list(TABLES.values())
    survivor, missing = target / names[0], target / names[1]

    survivor.write_bytes(b"SENTINEL-LOCAL-EDIT")  # locally modify a survivor
    missing.unlink()                               # and drop another -> incomplete
    assert not scenario_dataset_present(target)

    assert provision_scenario_dataset(target) is True

    assert scenario_dataset_present(target)
    # The sentinel edit was replaced wholesale, not kept.
    assert survivor.read_bytes() != b"SENTINEL-LOCAL-EDIT"
    # The whole directory equals a fresh committed-generator dataset.
    ref = tmp_path / "ref"
    ref.mkdir()
    generate_scenario(out_dir=ref)
    assert _dir_hash(target) == _dir_hash(ref)
    # No staging/backup sibling directories are left behind after the swap.
    assert [p.name for p in tmp_path.iterdir()
            if p.name.startswith(".synthetic.")] == []


def test_generation_failure_leaves_original_intact(tmp_path, monkeypatch):
    """If regeneration fails, the pre-existing (incomplete) directory is left
    exactly as it was — the swap never runs, so nothing is half-written or lost,
    and no staging directory is orphaned."""
    target = tmp_path / "synthetic"
    provision_scenario_dataset(target)
    names = list(TABLES.values())
    (target / names[1]).unlink()  # make it incomplete so provision will regen
    before = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated generation failure")

    monkeypatch.setattr(bootstrap, "generate_scenario", _boom)

    with pytest.raises(RuntimeError):
        provision_scenario_dataset(target)

    # Every surviving file is byte-identical, and no staging/backup was orphaned.
    after = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    assert after == before
    assert [p.name for p in tmp_path.iterdir()
            if p.name.startswith(".synthetic.")] == []


# F-023: replacing an existing dataset takes two sequential renames and the
# target path does not exist between them. That window cannot be tested away, so
# it is tested AT — each rename is failed in turn while every other rename is
# performed for real, so the on-disk aftermath asserted below is the real one.


class _SimulatedKill(BaseException):
    """Stands in for a process death mid-swap.

    Derived from ``BaseException``, not ``Exception``, so it models an
    interruption rather than an ordinary error the code might expect.
    """


class _ReplaceFaults:
    """Patches ``bootstrap.os`` so chosen ``os.replace`` calls fail.

    Call 1 is ``target -> backup``, call 2 is ``staging -> target``, and call 3
    is the in-process rollback ``backup -> target``. Any call not selected is
    performed for real; every other ``os`` attribute is delegated untouched, so
    only the renames are affected.
    """

    def __init__(self, *fail_on: int, before_call: dict | None = None) -> None:
        self._fail_on = set(fail_on)
        self._before = before_call or {}
        self._real_replace = os.replace
        self.calls = 0

    def __getattr__(self, name):
        return getattr(os, name)

    def replace(self, src, dst):
        self.calls += 1
        # ``before_call`` runs just before a chosen rename, which is how a
        # concurrent boot's interleaving is modelled in one process.
        hook = self._before.get(self.calls)
        if hook is not None:
            hook()
        if self.calls in self._fail_on:
            raise _SimulatedKill(f"injected rename failure at call {self.calls}")
        return self._real_replace(src, dst)


def _siblings(tmp_path: Path) -> list[str]:
    """Names of every staging/backup sibling the swap may have left behind."""
    return sorted(p.name for p in tmp_path.iterdir()
                  if p.name.startswith(".synthetic."))


def _make_incomplete(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    """A complete dataset with one table removed, plus its surviving bytes."""
    target = tmp_path / "synthetic"
    provision_scenario_dataset(target)
    (target / list(TABLES.values())[1]).unlink()
    assert not scenario_dataset_present(target)
    return target, {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}


def test_failure_at_first_rename_leaves_original_untouched(tmp_path, monkeypatch):
    """Fault at rename 1 (target -> backup): the swap never begins, so the
    pre-existing directory is byte-identical and nothing is orphaned."""
    target, before = _make_incomplete(tmp_path)
    faults = _ReplaceFaults(1)
    monkeypatch.setattr(bootstrap, "os", faults)

    with pytest.raises(_SimulatedKill):
        provision_scenario_dataset(target)

    assert faults.calls == 1
    assert {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()} == before
    assert _siblings(tmp_path) == []


def _kill_between_renames(tmp_path: Path, monkeypatch, *, backup_complete: bool):
    """Leave the on-disk state a process killed between the two renames leaves.

    Rename 1 succeeds, rename 2 fails, and the in-process rollback fails too — a
    killed process runs no handler. With ``backup_complete``, the missing table is
    restored just before rename 1, modelling a concurrent boot whose own swap
    landed after this call's completeness check: the directory moved aside is then
    a FINISHED dataset, which is the case recovery exists for.
    """
    target = tmp_path / "synthetic"
    provision_scenario_dataset(target)
    complete_hash = _dir_hash(target)
    victim = target / list(TABLES.values())[1]
    survivor_bytes = victim.read_bytes()
    victim.unlink()

    hooks = {1: lambda: victim.write_bytes(survivor_bytes)} if backup_complete else {}
    faults = _ReplaceFaults(2, 3, before_call=hooks)
    monkeypatch.setattr(bootstrap, "os", faults)
    with pytest.raises(_SimulatedKill):
        provision_scenario_dataset(target)
    return target, complete_hash


def test_kill_between_renames_leaves_the_dataset_under_the_backup_name(
    tmp_path, monkeypatch
):
    """The window is real, and this pins exactly what it costs: with a concurrent
    boot's finished dataset moved aside, the target path is left absent and the
    only complete copy of the data sits under the hidden backup name."""
    target, complete_hash = _kill_between_renames(
        tmp_path, monkeypatch, backup_complete=True
    )

    assert not target.exists()  # the observable missing-target window, realized
    assert not scenario_dataset_present(target)
    backups = list(tmp_path.glob(f"{bootstrap._backup_prefix(target)}*"))
    assert len(backups) == 1
    assert scenario_dataset_present(backups[0])
    assert _dir_hash(backups[0]) == complete_hash  # intact, and only there


def test_next_boot_restores_the_orphaned_backup(tmp_path, monkeypatch):
    """Startup recovery: the next boot finds the orphaned complete backup and
    restores it rather than regenerating around it."""
    target, complete_hash = _kill_between_renames(
        tmp_path, monkeypatch, backup_complete=True
    )
    monkeypatch.undo()  # the process died; a fresh boot starts here

    assert provision_scenario_dataset(target) is False  # restored, not regenerated

    assert scenario_dataset_present(target)
    assert _dir_hash(target) == complete_hash
    # The backup is consumed; the orphaned staging directory is deliberately left
    # alone (a concurrent boot may own one) — see _recover_interrupted_swap.
    assert not list(tmp_path.glob(f"{bootstrap._backup_prefix(target)}*"))
    assert all(name.startswith(".synthetic.staging-")
               for name in _siblings(tmp_path))


def test_next_boot_regenerates_when_the_orphaned_backup_is_incomplete(
    tmp_path, monkeypatch
):
    """The ordinary single-process kill: the swap displaced the incomplete set
    that triggered it, so there is nothing worth restoring. The next boot
    discards that backup and regenerates, landing byte-identical."""
    target, complete_hash = _kill_between_renames(
        tmp_path, monkeypatch, backup_complete=False
    )
    assert not target.exists()
    backups = list(tmp_path.glob(f"{bootstrap._backup_prefix(target)}*"))
    assert len(backups) == 1 and not scenario_dataset_present(backups[0])
    monkeypatch.undo()

    assert provision_scenario_dataset(target) is True  # regenerated, not restored

    assert _dir_hash(target) == complete_hash
    assert not list(tmp_path.glob(f"{bootstrap._backup_prefix(target)}*"))


def test_failure_at_second_rename_rolls_back_in_process(tmp_path, monkeypatch):
    """Fault at rename 2 with the rollback intact: the existing behavior stands —
    the original is put back in-process and nothing is orphaned."""
    target, before = _make_incomplete(tmp_path)
    faults = _ReplaceFaults(2)
    monkeypatch.setattr(bootstrap, "os", faults)

    with pytest.raises(_SimulatedKill):
        provision_scenario_dataset(target)

    assert faults.calls == 3  # aside, failed swap, rollback
    assert {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()} == before
    assert _siblings(tmp_path) == []


def test_incomplete_orphaned_backup_is_discarded_not_restored(tmp_path):
    """Recovery never installs a worse dataset than regeneration would produce: an
    orphaned backup that is itself incomplete is discarded, and the ordinary
    regeneration runs."""
    target = tmp_path / "synthetic"
    seed_dir = tmp_path / "seed"
    provision_scenario_dataset(seed_dir)
    backup = tmp_path / f"{bootstrap._backup_prefix(target)}.synthetic.staging-x"
    seed_dir.rename(backup)
    (backup / list(TABLES.values())[0]).unlink()  # the backup is incomplete too
    assert not target.exists()

    assert provision_scenario_dataset(target) is True  # regenerated, not restored

    assert not backup.exists()
    ref = tmp_path / "ref"
    ref.mkdir()
    generate_scenario(out_dir=ref)
    assert _dir_hash(target) == _dir_hash(ref)


def test_boot_regen_is_byte_identical_to_committed_generator(tmp_path):
    """Determinism: the boot hook's output equals the committed generator's,
    byte-for-byte (same seed, same code path) — the deploy path can never drift
    from the local/CI path."""
    boot_dir = tmp_path / "boot"
    ref_dir = tmp_path / "ref"
    boot_dir.mkdir()
    ref_dir.mkdir()

    provision_scenario_dataset(boot_dir)
    generate_scenario(out_dir=ref_dir)  # the committed generator, default seed

    assert _dir_hash(boot_dir) == _dir_hash(ref_dir)


def test_default_hook_runs_at_most_once_per_process():
    """The default boot hook is memoized: a second call is served from cache,
    so repeated boots within one process touch the filesystem only once.

    (Runs against the real SYNTHETIC_DIR, which the documented local/CI flow
    populates before pytest, so this is a no-op regeneration-wise.)
    """
    ensure_default_scenario_dataset.cache_clear()
    first = ensure_default_scenario_dataset()
    second = ensure_default_scenario_dataset()

    assert first == second
    assert ensure_default_scenario_dataset.cache_info().hits >= 1
