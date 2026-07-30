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

import re
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


# --- Part IV counterparty-designation lifecycle panel (V2) ------------------
#
# The counterparty-lifecycle panel renders only for a counterparty_service
# designation, so these drive the shared sweep-mode app to DES-2026-0009
# (Kavelith Digital Exchange, the synthetic designated VASP). Reuses the
# module-scoped ``sweep_app_identity`` fixture (a sweep-mode app selected per
# test) rather than spinning a FOURTH AppTest — AppTest is the most expensive
# tenant, and the fixture is just "sweep mode, pick a designation", which is
# exactly what this needs. The three exposed personas map to three DIFFERENT
# dispositions (unblock / offboard / hold).

_COUNTERPARTY = "DES-2026-0009"


def test_counterparty_lifecycle_renders_dispositions_plain(sweep_app_identity):
    from app.streamlit_app import _CP_DISPOSITION_LABEL, _CP_STATE_LABEL

    at = _select(sweep_app_identity, _COUNTERPARTY)
    assert not at.exception
    text = _all_text(at)

    assert "Counterparty-designation lifecycle" in text
    # The three exposed customers render three DIFFERENT dispositions, each through
    # its plain proposal label — never the raw outcome slug (two-register boundary).
    for outcome in ("propose_unblock", "propose_offboard", "hold_pending"):
        assert _CP_DISPOSITION_LABEL[outcome] in text
        assert outcome not in text, f"raw outcome slug leaked to screen: {outcome}"
    # Lifecycle states render through their plain labels; no raw state slug reaches
    # the screen. The two proposal-terminal states (Marta's unblock, Aron's
    # offboard) are present in plain form.
    assert _CP_STATE_LABEL["unblock_proposed"] in text
    assert _CP_STATE_LABEL["offboard_proposed"] in text
    for state in ("exposure_detected", "notification_drafted",
                  "acknowledgment_recorded", "stop_dealing_verified",
                  "unblock_proposed", "offboard_proposed"):
        assert state not in text, f"raw lifecycle state slug leaked to screen: {state}"


def test_counterparty_lifecycle_rider_phrasing_and_notification(sweep_app_identity):
    from app.streamlit_app import _RFI_STATUS_LABEL

    at = _select(sweep_app_identity, _COUNTERPARTY)
    assert not at.exception
    text = _all_text(at)

    # PHRASING RIDER (PM ruling, binding): propose_unblock renders as "Propose
    # lifting the sweep-proposed restriction (pending human review)" — NEVER bare
    # "propose unblock" (these review-subject personas carry no visible hold row).
    assert ("Propose lifting the sweep-proposed restriction (pending human review)"
            in text)
    # The no-auto-unblock posture is stated plainly on the surface itself.
    assert "No hold is ever lifted here" in text

    # The drafted (never sent) customer notification renders with its plain status,
    # and names the counterparty's PUBLIC designation (the sayable scope).
    assert _RFI_STATUS_LABEL["drafted_pending_human_review"] in text
    assert "drafted_pending_human_review" not in text
    assert "Kavelith Digital Exchange" in text
    # Two-register: the disposition/notification provenance keeps real table names
    # (the acknowledgments ledger and the accounts row the notification grounds to).
    assert "acknowledgments" in text
    assert "accounts[" in text


# --- Simulated list-feed update (DEMO FIX 2) --------------------------------
#
# The "Simulate list-feed update (advanced)" source is a manual stand-in for an
# inbound list-feed event. The example payloads are the regression guard: the
# valid one is serialized FROM the Designation model, so it can never drift out
# of schema again (the prior hand-written example silently lost four required
# fields when Part I-B added them).


def test_example_designation_payloads_valid_and_malformed():
    """The pure anti-drift guarantee (no app spin): the generated valid payload
    parses through the same fail-closed boundary the UI uses, and the malformed
    one is rejected. If a future required field is added to the model, the
    generator's constructor breaks here loudly rather than shipping a stale,
    invalid example in the demo."""
    from app.streamlit_app import _example_designation_payloads
    from okojo.sweep import DesignationParseError, parse_designation

    valid_json, malformed_json = _example_designation_payloads()

    d = parse_designation(valid_json)          # must round-trip through the boundary
    assert d.designation_id == "DES-2026-9001"
    assert d.list_type == "sdn_style"

    with pytest.raises(DesignationParseError):
        parse_designation(malformed_json)      # missing required fields → rejected


@pytest.fixture(scope="module")
def sweep_app_simulate(data_dir):
    """A sweep-mode AppTest switched to the simulate-list-feed source. Distinct
    module-scoped instance (the button clicks below mutate widget state, so it
    must not share the read-only ``sweep_app`` / ``sweep_app_identity``)."""
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    import streamlit as st
    import okojo.connectors.store as store_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(store_mod, "SYNTHETIC_DIR", data_dir)
    st.cache_resource.clear()

    at = AppTest.from_file(str(_APP), default_timeout=60)
    at.run()
    at.radio(key="app_mode").set_value("Designation sweep").run()
    at.radio(key="sweep_source").set_value(
        "Simulate list-feed update (advanced)").run()
    yield at

    mp.undo()
    st.cache_resource.clear()


def test_simulate_option_and_verbatim_caption(sweep_app_simulate):
    at = sweep_app_simulate
    assert not at.exception
    # The source option is renamed (calibrated: it SIMULATES an inbound event).
    assert ("Simulate list-feed update (advanced)"
            in at.radio(key="sweep_source").options)
    # The PM-approved caption is present verbatim (distinctive substrings).
    caps = " ".join(c.value for c in at.caption)
    assert "This box simulates that inbound event." in caps
    assert ("pass the same fail-closed validation before anything runs" in caps)
    # No claim of live connectivity — calibrated "simulates / arrives".
    assert "simulates" in caps.lower()


def test_simulate_malformed_payload_rejected_fail_closed(sweep_app_simulate):
    at = sweep_app_simulate
    at.button(key="sweep_load_malformed").click().run()
    assert not at.exception
    # The fail-closed rejection renders; nothing runs past the boundary.
    errs = " ".join(e.value for e in at.error).lower()
    assert "rejected (fail-closed)" in errs


def test_simulate_valid_payload_runs_sweep(sweep_app_simulate):
    at = sweep_app_simulate
    at.button(key="sweep_load_valid").click().run()
    assert not at.exception
    assert not at.error
    # The valid example is a company touching nothing in the ledger → the clean
    # false-positive path renders (worksheet section present, no exception).
    text = _all_text(at)
    assert "Remediation worksheet" in text


# --------------------------------------------------------------------------- #
# Phase 9 Slice 3: the Audit Narrator's two-register rendering.
#
# The sweep audit section is checked live via the existing module-scoped
# ``sweep_app`` fixture (no new app spin). The case-family rendering and the
# broken-chain break report are checked against the shared render helper through
# a recording stand-in for streamlit — a pure call, again no app spin.
# --------------------------------------------------------------------------- #
# raw record action slugs that must live ONLY in the raw hash-chain dataframe,
# never in the narrative register (markdown / caption).
_NARRATIVE_SLUGS = ("sweep_open", "sweep_complete", "exposure_sweep",
                    "block_verify", "escalations_draft", "name_screen")


def _lead_num(line):
    """The record seq a narrative line is numbered with (e.g. '**3.** ...' or
    '3. · ...' or '3. Chain verification FAILED ...'), or None for an unnumbered
    line such as the section header."""
    m = re.match(r"^\*{0,2}(\d+)\.", line)
    return int(m.group(1)) if m else None


def _provenance_df(at):
    for d in at.dataframe:
        cols = list(d.value.columns)
        if {"seq", "hash", "register"} <= set(cols):
            return d.value
    raise AssertionError("narrative provenance dataframe not rendered")


def test_sweep_audit_narrator_renders_plain(sweep_app):
    """The sweep audit section renders the narrator's plain sentences on screen,
    each numbered by its record seq; no raw record action slug leaks into the
    narrative register."""
    text = _all_text(sweep_app)
    assert "Opened the remediation sweep" in text
    assert "Completed the sweep" in text
    # the first sentence is numbered by its record seq (1) so it lines up with
    # the raw hash chain (the shared render helper numbers every line)
    assert re.search(r"\*\*1\.\*\*\s*Opened the remediation sweep", text)
    for slug in _NARRATIVE_SLUGS:
        assert slug not in text, slug


def test_sweep_audit_narrator_provenance_keeps_seq_hash(sweep_app):
    """The narrative provenance keeps each sentence's cited (seq, hash): seqs are
    1..N in order and every hash is a full 64-hex audit hash."""
    prov = _provenance_df(sweep_app)
    assert list(prov["seq"]) == list(range(1, len(prov) + 1))
    assert all(isinstance(h, str) and len(h) == 64 for h in prov["hash"])


class _StRecorder:
    """A minimal stand-in for the ``streamlit`` module: records what the render
    helper emits so the narrative + provenance are assertable without an app
    spin. Only the calls the helper makes are implemented."""

    def __init__(self):
        self.md, self.cap, self.err, self.df = [], [], [], []
        self.lines = []  # (kind, body) in render order, across md/cap/err

    def markdown(self, body, **_):
        self.md.append(body)
        self.lines.append(("md", body))

    def caption(self, body, **_):
        self.cap.append(body)
        self.lines.append(("cap", body))

    def error(self, body, **_):
        self.err.append(body)
        self.lines.append(("err", body))

    def dataframe(self, data, **_):
        self.df.append(data)

    def expander(self, *_, **__):
        recorder = self

        class _Ctx:
            def __enter__(self):
                return recorder

            def __exit__(self, *_exc):
                return False

        return _Ctx()


def test_case_audit_narrator_two_register_and_break(monkeypatch, conn, trust_uid, tmp_path):
    """The shared render helper narrates a CASE chain in two registers (actions
    prominent, setup de-emphasized), keeps (seq, hash) provenance, and renders a
    broken chain's break report — nothing past the break."""
    import app.streamlit_app as app_mod
    from okojo.orchestrator import run_case

    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "c", render_graph=False)

    rec = _StRecorder()
    monkeypatch.setattr(app_mod, "st", rec)
    app_mod._render_audit_narrative(res.audit_records, family="case",
                                    subject=f"uid:{trust_uid}")

    action_text = "\n".join(rec.md)
    setup_text = "\n".join(rec.cap)
    # two registers: a consequential action rendered prominent (markdown), a
    # versioned *_config stamp de-emphasized (caption)
    assert "Opened the case" in action_text
    assert any("policy into the record" in c for c in rec.cap)
    # no raw record slug leaks into either narrative register
    for slug in ("case_open", "agency_config", "case_recorded"):
        assert slug not in action_text and slug not in setup_text, slug
    # every narrative line is numbered by its record's seq, in render order, so
    # the narrative and the raw hash chain line up one-to-one
    rendered_seqs = [_lead_num(body) for kind, body in rec.lines
                     if kind in ("md", "cap", "err") and _lead_num(body) is not None]
    assert rendered_seqs == [r["seq"] for r in res.audit_records]
    # the case_open line (seq 1) is the prominent, numbered action line
    assert any(_lead_num(m) == res.audit_records[0]["seq"] and "Opened the case" in m
               for m in rec.md)
    # provenance keeps each sentence's cited (seq, hash), 1:1 with the chain
    prov = rec.df[-1]
    assert list(prov["seq"]) == [r["seq"] for r in res.audit_records]
    assert list(prov["hash"]) == [r["hash"] for r in res.audit_records]
    assert not rec.err  # a verified chain renders no break

    # a tampered chain renders its break report (via st.error) and nothing past it
    broken = [dict(r) for r in res.audit_records]
    mid = len(broken) // 2
    broken[mid]["detail"] = (broken[mid].get("detail") or "") + " TAMPERED"
    rec2 = _StRecorder()
    monkeypatch.setattr(app_mod, "st", rec2)
    app_mod._render_audit_narrative(broken, family="case")
    assert len(rec2.err) == 1 and "FAILED" in rec2.err[0] and "withheld" in rec2.err[0].lower()
    # the break line is numbered at the record where verification first failed
    assert _lead_num(rec2.err[0]) == broken[mid]["seq"]
    assert len(rec2.df[-1]) == 1  # break-report-only: a single cited record
    assert all("Plain-language narrative" in m for m in rec2.md)  # no action lines past the break
