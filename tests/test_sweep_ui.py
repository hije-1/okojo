"""Phase 8 Part I-B Slice S4: the sweep view's plain-language layer.

Verified headlessly via ``streamlit.testing.v1.AppTest`` — the demo pane is
non-compositing (viewport 0x0, the sidebar collapses out of the DOM), so
browser-driving a sidebar radio is impossible; AppTest drives the real widgets
in-process and is the correct tool here.

The two properties this slice must hold together:
  1. the sweep view renders the compliance-officer plain-language forms
     (system names, hold statuses, reconciliation-gap sentences, friendly
     action labels — no raw machine slugs); and
  2. the provenance ``source`` column STILL shows the real table names — the
     one deliberate exception, because a citation must name its store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


@pytest.fixture(scope="module")
def sweep_app(data_dir):
    """An AppTest over the real app, reading the session's synthetic data and
    switched into designation-sweep mode over the live domestic designation.

    Module-scoped: spinning the whole app up through AppTest is expensive, and
    every check below only READS the rendered view (no widget-state mutation),
    so the app is run once and shared. A manual MonkeyPatch is used because the
    ``monkeypatch`` fixture is function-scoped."""
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    import streamlit as st
    import okojo.connectors.store as store_mod

    # Point the app's connectors at the fixture data, not the repo's default
    # data/synthetic, and clear the cached resource so the patch takes effect.
    mp = pytest.MonkeyPatch()
    mp.setattr(store_mod, "SYNTHETIC_DIR", data_dir)
    st.cache_resource.clear()

    at = AppTest.from_file(str(_APP), default_timeout=60)
    at.run()
    at.radio(key="app_mode").set_value("Designation sweep").run()
    yield at

    mp.undo()
    st.cache_resource.clear()


def _worksheet_df(at):
    for d in at.dataframe:
        if "recommended action" in list(d.value.columns):
            return d.value
    raise AssertionError("worksheet dataframe not rendered")


# machine slugs that must never appear in the rendered view (outside the
# deliberately-exempt provenance source column).
_RAW_SLUGS = ("no_hold", "proposes_", "flags_", "missed_sync_block",
              "unrecorded_unblock", "reconciliation_gap", "exposed_unblocked")


def test_sweep_view_renders_plain_language_columns(sweep_app):
    from app.streamlit_app import _SYSTEM_LABEL

    ws = _worksheet_df(sweep_app)
    # System names render as compliance-officer plain language, not warehouse/admin.
    assert _SYSTEM_LABEL["warehouse"] in ws.columns
    assert _SYSTEM_LABEL["admin"] in ws.columns
    assert "reconciliation gap" in ws.columns

    # Hold statuses render plain; the raw slug never appears in these columns.
    statuses = set(ws[_SYSTEM_LABEL["warehouse"]]) | set(ws[_SYSTEM_LABEL["admin"]])
    assert "No hold" in statuses
    assert "no_hold" not in statuses


def test_sweep_view_action_labels_are_friendly(sweep_app):
    ws = _worksheet_df(sweep_app)
    actions = list(ws["recommended action"])
    # No machine action slug leaks into the rendered action column.
    assert not any(a.startswith(("proposes_", "flags_")) for a in actions)
    # The severe insider action (S3) renders through its friendly label.
    assert any("insider" in a.lower() for a in actions)


def test_sweep_view_gap_sentences_not_slugs(sweep_app):
    from okojo.sweep import GAP_TAXONOMY

    ws = _worksheet_df(sweep_app)
    gaps = [g for g in ws["reconciliation gap"] if g != "—"]
    assert gaps, "the live designation exposes reconciliation gaps"
    # Each rendered gap is the published compliance sentence, never the slug.
    for g in gaps:
        assert g in GAP_TAXONOMY.values()
        assert g not in GAP_TAXONOMY  # i.e. not a bare gap_type key


def test_sweep_view_surfaces_s3_flag_columns_in_plain_language(sweep_app):
    """The two S3 headline facts — exposure timing and the KYC gap — render as
    dedicated plain-language columns, not just inside statement text. (The third
    S3 flag, insider linkage, is already visible via its action label.)"""
    from app.streamlit_app import _ARTIFACT_LABEL, _TIMING_LABEL

    ws = _worksheet_df(sweep_app)
    assert "exposure timing" in ws.columns
    assert "KYC gap" in ws.columns

    # Timing renders through the friendly map; no raw machine value leaks.
    timings = set(ws["exposure timing"])
    assert timings <= (set(_TIMING_LABEL.values()) | {"—"})
    assert _TIMING_LABEL["timeless_control"] in timings
    assert _TIMING_LABEL["pre_designation"] in timings
    assert not any(t in timings for t in _TIMING_LABEL)  # no raw slugs

    # The KYC gap (KINGPIN's missing proof of address) renders in plain language.
    kyc = set(ws["KYC gap"])
    assert _ARTIFACT_LABEL["proof_of_address"] in kyc
    assert "proof_of_address" not in kyc  # not the raw artifact slug


def test_provenance_source_column_keeps_real_table_names(sweep_app):
    """The deliberate exception: the source column cites records, so it keeps the
    real table names even as everything else is plain-languaged."""
    ws = _worksheet_df(sweep_app)
    src_all = " ".join(ws["source"])
    # Real store names appear in the citations.
    assert "sanctions_hold_warehouse" in src_all
    assert "sanctions_hold_admin" in src_all


def test_sweep_view_no_uncaught_exception(sweep_app):
    assert not sweep_app.exception
