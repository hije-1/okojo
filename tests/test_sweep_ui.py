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


# --- Part II identity-resolution panels (T5b) -------------------------------
#
# The identity panels render only when a designation actually resolves an
# identity, so these drive the sweep to the identity designations (DES-0005
# has corroboration + ownership + proximity; DES-0006 has the possible-match
# corroboration + the identity-review RFI). Module-scoped app, driven per test.


@pytest.fixture(scope="module")
def sweep_app_identity(data_dir):
    """A second AppTest in sweep mode, driven to the identity designations.

    A distinct module-scoped instance (not the domestic ``sweep_app``) so the
    domestic tests never depend on which designation an identity test last
    selected; spun up once and shared across the identity checks."""
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    import streamlit as st
    import okojo.connectors.store as store_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(store_mod, "SYNTHETIC_DIR", data_dir)
    st.cache_resource.clear()

    at = AppTest.from_file(str(_APP), default_timeout=60)
    at.run()
    at.radio(key="app_mode").set_value("Designation sweep").run()
    yield at

    mp.undo()
    st.cache_resource.clear()


def _select(at, did):
    at.selectbox(key="sweep_designation_id").set_value(did).run()
    return at


def _all_text(at):
    """Every rendered text surface (markdown/write/caption/warning + expander
    labels and their children), flattened."""
    parts = []
    for coll in (at.markdown, at.caption, at.warning):
        parts.extend(el.value for el in coll)
    for exp in at.expander:
        parts.append(exp.label)
        for child in (exp.markdown, exp.caption):
            parts.extend(el.value for el in child)
    return "\n".join(parts)


def test_identity_corroboration_and_ownership_render(sweep_app_identity):
    from app.streamlit_app import _CORROBORATION_LABEL

    at = _select(sweep_app_identity, "DES-2026-0005")
    assert not at.exception
    text = _all_text(at)

    assert "Identity resolution" in text
    # Corroboration renders through the plain-language label, not the machine slug.
    assert _CORROBORATION_LABEL["corroborated_true_hit"] in text
    assert "corroborated_true_hit" not in text

    # Ownership walk: propagation, the stated control threshold, and both flags.
    assert "owned/controlled" in text
    assert "50%" in text  # OWNERSHIP_CONTROL_THRESHOLD stated on screen
    assert "Fictitious-executive flag" in text
    assert "Post-designation control change" in text
    # Two-register: the citations keep the real table names.
    assert "beneficial_ownership" in text or "officer_appointments" in text


def test_identity_proximity_renders_calibrated(sweep_app_identity):
    from app.streamlit_app import _PROXIMITY_SIGNAL_LABEL

    at = _select(sweep_app_identity, "DES-2026-0005")
    assert not at.exception
    text = _all_text(at)

    assert "Proximity ring" in text
    assert "candidate associate" in text
    assert "correlational" in text.lower()
    # Signal ids render through their plain-language labels, never the raw id.
    assert _PROXIMITY_SIGNAL_LABEL["shared_surname"] in text
    assert "shared_surname" not in text
    # Never asserts kinship as fact.
    for banned in ("is the sister", "is the brother", "is the spouse"):
        assert banned not in text.lower()


def test_identity_review_rfi_renders_with_status(sweep_app_identity):
    from app.streamlit_app import _CORROBORATION_LABEL, _RFI_STATUS_LABEL

    at = _select(sweep_app_identity, "DES-2026-0006")
    assert not at.exception
    text = _all_text(at)

    # The possible-match candidate is labelled for human review...
    assert _CORROBORATION_LABEL["possible_match_needs_human"] in text
    assert "possible_match_needs_human" not in text
    # ...and its identity-review RFI is drafted (never sent), with its status.
    assert "IDR-DES-2026-0006-0001" in text
    assert _RFI_STATUS_LABEL["drafted_pending_human_review"] in text
    assert "drafted_pending_human_review" not in text
    # The drafted RFI's own text is present (its anti-tipping-off cleanliness is
    # asserted directly on the draft in tests/test_identity_rfi.py).
    assert "identity" in text.lower()
    # Two-register: the RFI citation keeps the real KYC table name.
    assert "kyc_identity_attributes" in text


# --- Part III geo-triangulation panel (U3) ----------------------------------
#
# The geo panel renders only for a TERRITORY designation, so these drive the
# shared sweep-mode app to DES-2026-0008 (Qazrun Free Zone, the synthetic
# territory). Reuses the module-scoped ``sweep_app_identity`` fixture (a
# sweep-mode app selected per test) rather than spinning a THIRD AppTest — that
# is the most expensive tenant, and the fixture is just "sweep mode, pick a
# designation", which is exactly what a geo test needs. The three surfaced
# demo cases map to three DIFFERENT proposals.

_TERRITORY = "DES-2026-0008"


def test_geo_triangulation_renders_three_proposals(sweep_app_identity):
    from app.streamlit_app import _GEO_PROPOSAL_LABEL

    at = _select(sweep_app_identity, _TERRITORY)
    assert not at.exception
    text = _all_text(at)

    assert "Geo triangulation" in text
    # A territory designates a geography, not a party — so there is no name screen.
    assert "no name screen" in text.lower()
    # The three demo proposals render through their plain labels, never the raw
    # outcome slug (the calibrated two-register boundary).
    for outcome in ("propose_edd_rfi", "propose_withdrawal_only_restriction",
                    "propose_full_block_and_escalate"):
        assert _GEO_PROPOSAL_LABEL[outcome] in text
        assert outcome not in text
    # The net presence score is shown in plain terms (N and its band).
    assert "net presence score" in text.lower()


def test_geo_signals_render_calibrated_plain_language(sweep_app_identity):
    from app.streamlit_app import _GEO_SIGNAL_LABEL

    at = _select(sweep_app_identity, _TERRITORY)
    assert not at.exception
    text = _all_text(at)

    # Signal ids render through their plain labels, never the raw id. (The
    # timezone id is the one deliberate exception: it is a substring of the
    # ``device_timezones`` table name that the two-register citation keeps —
    # so it is checked by its plain label, not the raw-absent set.)
    assert _GEO_SIGNAL_LABEL["vpn_slip"] in text
    assert _GEO_SIGNAL_LABEL["exclusive_carrier"] in text
    assert _GEO_SIGNAL_LABEL["device_timezone"] in text
    for raw in ("vpn_slip", "exclusive_carrier", "declared_residence",
                "ip_geolocation", "kyc_geography", "phone_prefix"):
        assert raw not in text, f"raw signal id leaked to screen: {raw}"
    # Calibrated: signals indicate *possible* presence, never proof.
    assert "possible presence" in text.lower()
    # VPN discipline stated positively: an obfuscation marker, never evidence.
    assert "obfuscation marker" in text.lower()
    assert "never" in text.lower() and "location evidence" in text.lower()


def test_geo_traveller_counter_evidence_and_edd_rfi_render(sweep_app_identity):
    from app.streamlit_app import _GEO_STALENESS_LABEL, _RFI_STATUS_LABEL

    at = _select(sweep_app_identity, _TERRITORY)
    assert not at.exception
    text = _all_text(at)

    # The ambiguous traveller's counter-evidence renders with its degraded
    # staleness (an EXPIRED residency card argues against presence but weakly);
    # expiry is never read as presence.
    assert "Counter-evidence" in text
    assert _GEO_STALENESS_LABEL["expired"] in text
    # The KYC-refresh control gap surfaces separately from any location signal.
    assert "Control gaps" in text
    # The EDD RFI is drafted (never sent), rendered with its plain status.
    assert _RFI_STATUS_LABEL["drafted_pending_human_review"] in text
    assert "drafted_pending_human_review" not in text
    # Two-register: the dossier citations keep the real table names.
    assert "ip_logs" in text
    assert "kyc_artifact_validity" in text
