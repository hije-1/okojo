"""Case-mode UI: the Sanctions and Tells tabs' plain-language layer (no raw slugs).

Companion to ``test_sweep_ui.py`` (which holds the sweep view to the same
standard). Three properties:

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
  3. the **Tells** tab attributes each remark to its author (the sending side of
     the transaction, resolved to an account of record), marks subject-authored
     rows and groups them first, renders the category in plain language (no raw
     ``illicit_phrase`` / ``control_alias`` slug), and cites the analyst note's
     source per row. Verified on the rendered AppTest dataframe, plus a pure-logic
     check of the attribution resolver (no extra app spin — the module-scoped
     ``case_app`` is reused).

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

# The remark-tell category slugs that must never reach the Tells table (they
# stay the miner's tested contract, ``RemarkTell.category``).
_TELL_SLUGS = ("illicit_phrase", "control_alias")


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


def _tells_df(at):
    """The Tells-tab dataframe, found by its distinctive attribution column."""
    for d in at.dataframe:
        if "remark author" in list(d.value.columns):
            return d.value
    raise AssertionError("tells dataframe not rendered")


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


# --------------------------------------------------------------------------- #
# Tells tab — attribution, plain-language category, note provenance             #
# --------------------------------------------------------------------------- #
def test_tells_tab_attribution_and_labels_render(case_app):
    """The Tells table gains its structural attribution column, plain-language
    category labels (no raw slug), and a per-row note-source citation."""
    from app.streamlit_app import _TELL_CATEGORY_LABEL

    assert not case_app.exception
    df = _tells_df(case_app)
    cols = list(df.columns)
    for c in ("scope", "remark author", "type", "match strength",
              "analyst note (curated)", "note source", "source"):
        assert c in cols, f"tells table missing the {c!r} column"

    # Category renders in plain language — the raw slug never reaches the screen.
    joined = " | ".join(str(v) for row in df.itertuples(index=False) for v in row)
    for slug in _TELL_SLUGS:
        assert slug not in joined, f"raw tell category slug {slug!r} leaked into the UI"
    assert set(df["type"]) <= set(_TELL_CATEGORY_LABEL.values())

    # Attribution is plain name + uid (default subject authors ≥1 tell of record).
    assert any("uid " in str(a) for a in df["remark author"]), \
        "the remark-author column must resolve to a plain name + uid"

    # Every row cites its note source; phrase matches cite the curated registry.
    assert all(str(s).strip() for s in df["note source"]), "every note must cite a source"
    phrase_rows = df[df["type"] == _TELL_CATEGORY_LABEL["illicit_phrase"]]
    assert not phrase_rows.empty, "the default subject exercises a phrase match"
    assert all("signal-phrase registry[" in str(s) for s in phrase_rows["note source"]), \
        "a phrase-match note must cite the signal-phrase registry key"


def test_tell_author_resolves_the_remark_author_side(conn, trust_uid):
    """Pure-logic check of the attribution resolver (no app spin): a ``uid:``
    sender resolves to that account; an on-chain sending address resolves to its
    controller of record in the address book. The default subject's own
    controller-wallet remark therefore attributes back to the subject."""
    from app.streamlit_app import _tell_author
    from okojo.entity import build_backbone
    from okojo.remarks.miner import mine_remarks

    tells = mine_remarks(conn, backbone=build_backbone(conn))
    tx_by_id = {t["tx_id"]: t for t in conn.all_transactions()}
    abk_by_id = {str(e["entry_id"]): e for e in conn.address_book()}

    subject_authored = 0
    for h in tells:
        label, uid = _tell_author(conn, h, tx_by_id)
        if h.source_kind == "address_book":
            # an address-book label attributes to the customer who saved it
            entry = abk_by_id[h.tx_id]
            assert uid == int(entry["uid"])
            assert f"uid {uid}" in label and "saved-address label" in label
        else:
            tx = tx_by_id[h.tx_id]
            from_ref = str(tx["from_ref"])
            if from_ref.startswith("uid:"):
                # a KYC account sender resolves to itself, name + uid
                assert uid == int(from_ref.split(":", 1)[1])
                assert f"uid {uid}" in label
            else:
                # an on-chain sender resolves via the address book's controller_uid
                addr = conn.get_address(from_ref)
                expected = addr["controller_uid"] if addr is not None else None
                if expected is not None:
                    assert uid == int(expected)
                    assert "via address" in label
        if uid == trust_uid:
            subject_authored += 1

    # The default subject (the trust) authored at least one tell — its saved
    # "aggregation wallet" / "client custody" address-book labels — so the
    # subject-marker path is genuinely exercised.
    assert subject_authored >= 1


def test_tells_scope_marker_tracks_remark_author_p8g(case_app, conn, trust_uid):
    """P8-G (UI). The **◆ this subject** marker is not cosmetic — it partitions
    the table by remark-author, and subject rows are grouped first.

    Falsification (quoted in the slice report): swapping the equality to
    ``assert rendered == set(df['tx_id'])`` — i.e. claiming *every* tell is the
    subject's — goes red with
    'the scope marker must track the remark-author side, not all rows'.
    """
    from app.streamlit_app import _tell_author
    from okojo.entity import build_backbone
    from okojo.remarks.miner import mine_remarks

    assert not case_app.exception
    df = _tells_df(case_app)

    # Independently recompute which tells the default subject authored. Resolve
    # each rendered row via its source record (transaction OR address-book
    # label), the same author logic the table uses.
    tx_by_id = {t["tx_id"]: t for t in conn.all_transactions()}
    tell_by_id = {h.tx_id: h for h in mine_remarks(conn, backbone=build_backbone(conn))}
    expected = {
        tx_id for tx_id in df["tx_id"]
        if tx_id in tell_by_id
        and _tell_author(conn, tell_by_id[tx_id], tx_by_id)[1] == trust_uid
    }
    assert expected, "the default subject authors ≥1 tell (else the check is vacuous)"

    scopes = list(df["scope"])
    rendered = {
        tx_id for tx_id, sc in zip(df["tx_id"], scopes) if "this subject" in str(sc)
    }
    assert rendered == expected, \
        "the scope marker must track the remark-author side, not all rows"

    # Subject-authored rows are grouped first (all before any dataset-wide row).
    first_wide = next((i for i, s in enumerate(scopes) if "this subject" not in str(s)),
                      len(scopes))
    assert all("this subject" in str(s) for s in scopes[:first_wide]), \
        "subject-authored rows must be grouped first"
