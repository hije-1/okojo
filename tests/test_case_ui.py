"""Case-mode UI: the Sanctions tab's plain-language layer (no raw slugs).

Companion to ``test_sweep_ui.py`` (which holds the sweep view to the same
standard). Two properties:

  1. the case-mode on-chain exposure view renders the compliance-officer
     plain-language forms for its risk-score reason codes and the
     score-decomposition ``kind`` (verified via ``streamlit.testing.v1.AppTest``);
  2. (v1.1) the subject-as-seed **designation posture** at the top of the tab
     renders its three-state badge, the always-visible dismissal line, the
     exposure / territory / network / coverage lines — each in plain language,
     no raw designation slug — and its badge register faithfully tracks the
     badge state. The per-state and no-slug checks drive the render helper
     directly through a recorder (the audit-trail tab legitimately carries the
     raw record slugs, so a whole-app text sweep would be the wrong instrument);
     one AppTest proves the section renders end-to-end in the real app.

The raw machine slugs stay the model's tested contract, never the screen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from okojo.designation_check import run_designation_check

_APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"

# The underscore-compound designation slugs that must never reach the screen
# (bare words like "name"/"variant"/"address" are ordinary English and render
# inside plain-language labels, so only the machine-compound forms are checked).
_POSTURE_SLUGS = (
    "no_match", "possible_match", "match_corroborated",
    "corroborated_true_hit", "possible_match_needs_human", "name_only_dismissed",
    "pre_designation", "post_designation", "timeless_control",
    "exposure_detected", "notification_drafted", "acknowledgment_recorded",
    "stop_dealing_verified", "unblock_proposed", "offboard_proposed",
)


@pytest.fixture(scope="module")
def case_app(data_dir):
    """An AppTest over the real app in its default *case-investigation* mode,
    reading the session's synthetic data. Module-scoped: the app is expensive to
    spin and every check only READS the default subject's rendered view."""
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    import streamlit as st
    import okojo.connectors.store as store_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(store_mod, "SYNTHETIC_DIR", data_dir)
    st.cache_resource.clear()

    at = AppTest.from_file(str(_APP), default_timeout=60)
    at.run()  # default radio == "Case investigation"
    yield at

    mp.undo()
    st.cache_resource.clear()


def _risk_df(at):
    for d in at.dataframe:
        if "hops_to_sanctioned" in list(d.value.columns):
            return d.value
    raise AssertionError("on-chain risk dataframe not rendered for the subject")


def _score_breakdown_text(at):
    """The 'Score breakdown — show the math' expander's markdown — the surface
    that names each score's decomposition ``kind``. Scoped deliberately: the raw
    audit-trail records elsewhere legitimately carry machine field names (e.g.
    ``gas_only_accounts=0``), the same way provenance citations keep real store
    names — so a whole-app text sweep would be the wrong instrument here."""
    for exp in at.expander:
        if exp.label.startswith("Score breakdown"):
            return "\n".join(el.value for el in exp.markdown)
    raise AssertionError("score-breakdown expander not rendered")


def test_sanctions_tab_risk_reasons_render_plain_language(case_app):
    from app.streamlit_app import _RISK_REASON_LABEL

    assert not case_app.exception
    rdf = _risk_df(case_app)

    # The exposure table exists and the default subject actually scores, so the
    # reason codes are genuinely exercised (not a vacuous pass).
    reason_cells = [c for c in rdf["reasons"] if c]
    assert reason_cells, "the default subject has scored exposure with reasons"

    # No raw reason slug leaks into the rendered column...
    joined = " | ".join(reason_cells)
    for slug in _RISK_REASON_LABEL:
        assert slug not in joined, f"raw reason slug {slug!r} leaked into the UI"
    # ...and every rendered token is a published plain-language phrase.
    rendered = {tok.strip() for cell in reason_cells for tok in cell.split(",")}
    assert rendered <= set(_RISK_REASON_LABEL.values())

    # The odd slug-named boolean column was renamed to plain language.
    assert "on money-flow path" in rdf.columns
    assert "money_flow" not in rdf.columns


def test_sanctions_tab_decomposition_kind_renders_plain_language(case_app):
    from app.streamlit_app import _RISK_KIND_LABEL

    assert not case_app.exception
    text = _score_breakdown_text(case_app)
    # The "show the math" decomposition names its kind in plain language; the raw
    # slugs (money_flow / gas_only) never reach this surface.
    for slug in _RISK_KIND_LABEL:
        assert slug not in text, f"raw decomposition kind {slug!r} leaked into the UI"
    # At least the money-flow kind is exercised by the default subject.
    assert _RISK_KIND_LABEL["money_flow"] in text


# --------------------------------------------------------------------------- #
# v1.1 designation posture — render helper driven through a recorder            #
# --------------------------------------------------------------------------- #
class _PostureRecorder:
    """A minimal stand-in for ``streamlit`` that records what
    ``_render_designation_posture`` emits — so every badge register, the
    always-visible dismissal line, and the no-slug property are assertable
    without an app spin (and without the audit tab's legitimately-raw records).
    The helper never opens an expander; ``expander_calls`` proves it (Q2b:
    the dismissal is never tucked away)."""

    def __init__(self):
        # storage lists are named apart from the st.* method names so the
        # methods are not shadowed by same-named instance attributes.
        self.md, self.cap = [], []
        self.ok, self.warn, self.err, self.note = [], [], [], []
        self.expander_calls = 0

    def markdown(self, body, **_):
        self.md.append(body)

    def caption(self, body, **_):
        self.cap.append(body)

    def success(self, body, **_):
        self.ok.append(body)

    def warning(self, body, **_):
        self.warn.append(body)

    def error(self, body, **_):
        self.err.append(body)

    def info(self, body, **_):
        self.note.append(body)

    def expander(self, *_a, **_k):  # pragma: no cover - never called by the helper
        self.expander_calls += 1
        raise AssertionError("the posture must not tuck anything into an expander")

    def all_text(self) -> str:
        return "\n".join(self.md + self.cap + self.ok
                         + self.warn + self.err + self.note)


def _render_posture(monkeypatch, dc):
    import app.streamlit_app as app_mod
    rec = _PostureRecorder()
    monkeypatch.setattr(app_mod, "st", rec)
    app_mod._render_designation_posture(dc)
    return rec


def _no_posture_slug(rec):
    text = rec.all_text()
    for slug in _POSTURE_SLUGS:
        assert slug not in text, f"raw designation slug {slug!r} leaked into the UI"


@pytest.fixture()
def _corroborated_uid(ground_truth):
    for _d, per in ground_truth["corroboration_outcomes"].items():
        for uid, outcome in per.items():
            if outcome == "corroborated_true_hit":
                return int(uid)
    pytest.skip("no corroborated persona in the answer key")


@pytest.fixture()
def _dismissed_uid(ground_truth):
    for _d, per in ground_truth["corroboration_outcomes"].items():
        for uid, outcome in per.items():
            if outcome == "name_only_dismissed":
                return int(uid)
    pytest.skip("no dismissed persona in the answer key")


def test_posture_green_subject_success_register_and_coverage(monkeypatch, conn, trust_uid):
    from app.streamlit_app import _BADGE_LABEL

    dc = run_designation_check(conn, trust_uid, {trust_uid})
    rec = _render_posture(monkeypatch, dc)
    # GREEN -> the success register, never error/warning-as-badge.
    assert rec.ok and _BADGE_LABEL["no_match"] in rec.ok[0]
    assert not rec.err
    # The subject header names the subject; the coverage footer is present.
    assert any(f"uid {trust_uid}" in m for m in rec.md)
    assert any("Screened" in c and "designation(s)" in c for c in rec.cap)
    _no_posture_slug(rec)


def test_posture_green_subject_shows_exposure_as_warning(monkeypatch, conn, trust_uid):
    """Q2a: a GREEN badge with a live fund-flow exposure renders the exposure as
    a warning line beneath the badge — the green badge is not an all-clear for
    the whole block."""
    dc = run_designation_check(conn, trust_uid, {trust_uid})
    if not dc.flow_exposures:
        pytest.skip("the default subject carries no flow exposure in this scenario")
    rec = _render_posture(monkeypatch, dc)
    assert rec.ok  # badge is green
    assert any("Fund-flow exposure" in w for w in rec.warn)
    _no_posture_slug(rec)


def test_posture_red_subject_error_register_and_corroborated_hit(
        monkeypatch, conn, _corroborated_uid):
    from app.streamlit_app import _BADGE_LABEL, _CORROBORATION_LABEL

    dc = run_designation_check(conn, _corroborated_uid, {_corroborated_uid})
    rec = _render_posture(monkeypatch, dc)
    # RED -> the error register.
    assert rec.err and _BADGE_LABEL["match_corroborated"] in rec.err[0]
    assert not rec.ok
    # The corroborated hit renders in plain language (outcome + match kind).
    hits = "\n".join(rec.md)
    assert _CORROBORATION_LABEL["corroborated_true_hit"] in hits
    _no_posture_slug(rec)


def test_posture_dismissed_subject_green_with_standing_dismissal_line(
        monkeypatch, conn, _dismissed_uid):
    from app.streamlit_app import _BADGE_LABEL

    dc = run_designation_check(conn, _dismissed_uid, {_dismissed_uid})
    rec = _render_posture(monkeypatch, dc)
    # Q2b: an adjudicated collision is GREEN on the badge...
    assert rec.ok and _BADGE_LABEL["no_match"] in rec.ok[0]
    # ...but ALWAYS renders a standing, cited dismissal line (never in an
    # expander — the recorder raises if one is opened).
    assert rec.expander_calls == 0
    assert any("screened and dismissed" in w.lower() for w in rec.warn)
    assert any("source:" in c for c in rec.cap)  # the dismissal is cited
    _no_posture_slug(rec)


def test_posture_network_notice_names_the_matched_entity(
        monkeypatch, conn, trust_uid, ground_truth):
    """A cluster name-match surfaces as a network notice that NAMES the entity
    and its designation — never the subject's own badge."""
    from app.streamlit_app import _BADGE_LABEL

    des = next(d for d, uids in ground_truth["designation_name_match_uids"].items() if uids)
    match_uid = int(ground_truth["designation_name_match_uids"][des][0])
    dc = run_designation_check(conn, trust_uid, {trust_uid, match_uid})
    rec = _render_posture(monkeypatch, dc)
    notices = [m for m in rec.md if m.startswith("- uid") and str(match_uid) in m]
    assert notices, "a cluster name match must render as a named network notice"
    assert des in notices[0]  # the designation is named
    assert rec.ok and _BADGE_LABEL["no_match"] in rec.ok[0]  # badge unmoved
    _no_posture_slug(rec)


def test_posture_p8g_register_break_red_vs_green(monkeypatch, conn, trust_uid, _corroborated_uid):
    """P8-G (UI). The badge REGISTER must track the badge state: a corroborated
    subject renders via st.error (not st.success); a clean subject renders via
    st.success (not st.error). Swapping either assertion goes red — the register
    is not cosmetic, it is the posture.

    Red demonstration (quoted in the slice report): asserting the corroborated
    subject renders st.success fails with
    'the RED subject must not render a success badge'.
    """
    red = run_designation_check(conn, _corroborated_uid, {_corroborated_uid})
    green = run_designation_check(conn, trust_uid, {trust_uid})

    rec_red = _render_posture(monkeypatch, red)
    assert rec_red.err and not rec_red.ok, "the RED subject must not render a success badge"

    rec_green = _render_posture(monkeypatch, green)
    assert rec_green.ok and not rec_green.err, "the GREEN subject must not render an error badge"


def test_posture_renders_end_to_end_in_app(case_app):
    """One real AppTest: the posture section renders in situ on the default
    (GREEN) subject — the header, the success badge, the coverage footer — and
    the ledger-wide section now heads the wider screens (the old subject-scope
    caption moved down, per the section-break restructure)."""
    assert not case_app.exception
    alerts = [el.value for el in case_app.success]
    md = [el.value for el in case_app.markdown]
    caps = [el.value for el in case_app.caption]

    assert any("Designation & sanctions posture" in m for m in md), "posture header missing"
    assert any("No designation match" in a for a in alerts), "green badge missing"
    assert any("Screened" in c and "designation(s)" in c for c in caps), "coverage footer missing"
    assert any("Ledger-wide screening context" in m for m in md), "ledger-wide section header missing"
    # the old subject-scope caption text is gone (its scope role moved down)
    assert not any("this subject's** accounts only" in c for c in caps)
