"""Case-mode UI: the Sanctions tab's plain-language layer (no raw slugs).

Companion to ``test_sweep_ui.py`` (which holds the sweep view to the same
standard). The property here: the case-mode on-chain exposure view renders the
compliance-officer plain-language forms for its risk-score reason codes and the
score-decomposition ``kind`` — the raw machine slugs stay the model's tested
contract (``RiskScore.reasons`` / ``ScoreDecomposition.kind``), never the screen.
Verified headlessly via ``streamlit.testing.v1.AppTest``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


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
