"""Boot-time synthetic-data bootstrap (Phase 10 B2).

Covers both branches of the boot hook — missing dataset regenerates and loads;
present dataset is left byte-untouched — and pins the determinism promise: a
boot-regenerated dataset equals a committed-generator one, byte-for-byte.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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
