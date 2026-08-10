"""Guided-walkthrough narrative layer — the display-only guided-tour bands.

The walkthrough is a text/display feature over both modes: a sidebar toggle
(ON by default) shows a fixed, Jennifer-approved narrative band above each tab
bar (the mode intro) and at the top of every tab. The prose is FROZEN — these
tests assert it renders **verbatim**, so an accidental reword is caught.

Four properties, all through ``streamlit.testing.v1.AppTest`` (element getters
recurse across ``st.tabs``, so one run per mode surfaces every tab's band):

  1. toggle ON (default) → the mode intro + every tab's band renders, verbatim
     (case mode over its 9 tabs; sweep mode over its 6);
  2. toggle OFF → not one band renders, in either mode (the toggle is the only
     behaviour this layer adds);
  3. verbatim guard / falsification (quoted red/green): the band renders the
     approved text, never a paraphrase.

The bands are the app's fixed constants (``_WT_CASE_INTRO`` / ``_WT_CASE`` /
``_WT_SWEEP_INTRO`` / ``_WT_SWEEP``), imported and asserted against the rendered
markdown — so this file and the app cannot silently disagree on the wording.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def _flat_markdown(at) -> str:
    """Every rendered markdown value joined — the walkthrough band is one
    ``st.markdown(..., unsafe_allow_html=True)`` HTML div, so its verbatim prose
    is a substring here. Getters recurse across tabs, so a single case-mode run
    surfaces all nine tab bands (and a sweep-mode run all six)."""
    return "\n".join(el.value for el in at.markdown)


def _spin(data_dir, *, timeout=90):
    """A fresh AppTest over the real app on the session's synthetic data. Callers
    that only READ a rendered view should prefer the module-scoped fixtures
    below; this bare helper is for the tests that mutate the toggle / mode."""
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

    import streamlit as st
    import okojo.connectors.store as store_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(store_mod, "SYNTHETIC_DIR", data_dir)
    st.cache_resource.clear()
    at = AppTest.from_file(str(_APP), default_timeout=timeout)
    return at, mp


@pytest.fixture(scope="module")
def wt_case_on(data_dir):
    """Case mode, walkthrough toggle at its default (ON). Module-scoped: the app
    is expensive to spin and this fixture is only READ (never mutated)."""
    import streamlit as st

    at, mp = _spin(data_dir)
    at.run()  # default radio == "Case investigation"; toggle defaults ON
    yield at
    mp.undo()
    st.cache_resource.clear()


@pytest.fixture(scope="module")
def wt_sweep_on(data_dir):
    """Designation-sweep mode, walkthrough toggle ON. Module-scoped, read-only."""
    import streamlit as st

    at, mp = _spin(data_dir)
    at.run()
    at.radio(key="app_mode").set_value("Designation sweep").run()
    yield at
    mp.undo()
    st.cache_resource.clear()


def test_toggle_on_renders_case_intro_and_every_tab_band_verbatim(wt_case_on):
    """ON (default), case mode: the mode intro and all nine tab bands render, and
    each renders the approved text VERBATIM (the constants are the app's own, so
    a reword in the app would fail this exact-substring check)."""
    from app.streamlit_app import _WT_CASE, _WT_CASE_INTRO

    assert not wt_case_on.exception
    flat = _flat_markdown(wt_case_on)

    assert _WT_CASE_INTRO in flat, "case mode intro band missing (toggle ON)"
    for key, text in _WT_CASE.items():
        assert text in flat, f"case tab band {key!r} missing or reworded (toggle ON)"


def test_toggle_on_renders_sweep_intro_and_every_tab_band_verbatim(wt_sweep_on):
    """ON, sweep mode: the mode intro and all six tab bands render verbatim."""
    from app.streamlit_app import _WT_SWEEP, _WT_SWEEP_INTRO

    assert not wt_sweep_on.exception
    flat = _flat_markdown(wt_sweep_on)

    assert _WT_SWEEP_INTRO in flat, "sweep mode intro band missing (toggle ON)"
    for key, text in _WT_SWEEP.items():
        assert text in flat, f"sweep tab band {key!r} missing or reworded (toggle ON)"


def test_toggle_off_hides_every_band_in_both_modes(data_dir):
    """OFF: not one band renders — in either mode. The toggle state lives in
    session state, so it holds across the mode switch; one spin covers both.
    (The only behaviour this layer adds is this switch — with it off the app is
    byte-for-byte its pre-walkthrough self.)"""
    import streamlit as st
    from app.streamlit_app import (
        _WT_CASE, _WT_CASE_INTRO, _WT_SWEEP, _WT_SWEEP_INTRO,
    )

    at, mp = _spin(data_dir)
    try:
        at.run()
        at.toggle(key="guided_walkthrough").set_value(False).run()
        assert not at.exception

        flat_case = _flat_markdown(at)
        assert _WT_CASE_INTRO not in flat_case, "case intro leaked with the toggle off"
        for key, text in _WT_CASE.items():
            assert text not in flat_case, f"case band {key!r} leaked with the toggle off"

        # switch to sweep mode; the toggle stays OFF (session state)
        at.radio(key="app_mode").set_value("Designation sweep").run()
        assert not at.exception
        flat_sweep = _flat_markdown(at)
        assert _WT_SWEEP_INTRO not in flat_sweep, "sweep intro leaked with the toggle off"
        for key, text in _WT_SWEEP.items():
            assert text not in flat_sweep, f"sweep band {key!r} leaked with the toggle off"
    finally:
        mp.undo()
        st.cache_resource.clear()


def test_walkthrough_verbatim_falsification(wt_case_on):
    """Falsification (quoted red/green): the band renders the APPROVED text, not
    a paraphrase.

    GREEN: with the toggle ON, the verbatim intro is a substring of the rendered
    markdown (asserted above and here).

    Red demonstration (quoted in the slice report): swapping the final assertion
    to ``assert reworded in flat`` — claiming a paraphrase ('research demo' for
    'research prototype') renders — goes red with
    'a reworded walkthrough band must never render — the text is frozen'.
    """
    from app.streamlit_app import _WT_CASE_INTRO

    flat = _flat_markdown(wt_case_on)
    assert _WT_CASE_INTRO in flat  # GREEN: verbatim present

    reworded = _WT_CASE_INTRO.replace("research prototype", "research demo")
    assert reworded != _WT_CASE_INTRO, "guard fixture: the reword must differ"
    assert reworded not in flat, \
        "a reworded walkthrough band must never render — the text is frozen"
