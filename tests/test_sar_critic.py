"""The SAR Critic: a deterministic FinCEN-rubric grade over the structured draft.

Grading is a pure function of the draft's claim ``element`` tags — no LLM, no
data access — so these tests build minimal drafts directly and assert the grade,
the ordered gap list, and the versioned config shape.
"""

from __future__ import annotations

from okojo.provenance import Provenance
from okojo.sar import (
    CRITIC_THRESHOLD,
    CRITIC_VERSION,
    FINCEN_RUBRIC,
    SarClaim,
    SarDraft,
    critic_config,
    critique,
)

_P = [Provenance(source="accounts", row_key="uid:1")]


def _draft(*elements: str) -> SarDraft:
    return SarDraft(
        subject_uid=1, subject_name="X", filing_note="", disclaimer="",
        claims=[SarClaim(element=e, statement=f"{e} claim.", provenance=_P) for e in elements],
    )


def _full_elements() -> list[str]:
    """One claim element that satisfies every rubric element."""
    return ["who", "what", "when", "where", "predicate", "how", "network", "onchain"]


def test_full_draft_meets_the_bar():
    crit = critique(_draft(*_full_elements()))
    assert crit.coverage == 1.0
    assert crit.meets_bar()
    assert crit.gaps() == []


def test_missing_elements_are_reported_as_gaps():
    # A base-shaped draft (who/what/network/tell) covers 4 of 8 rubric elements.
    crit = critique(_draft("who", "what", "network", "tell"))
    assert crit.coverage == 0.5
    assert not crit.meets_bar()
    assert crit.gap_keys() == ["when", "where", "why", "how"]


def test_advisory_satisfies_why_and_tell_satisfies_subject_network():
    # 'why' passes via an advisory claim (not only an explicit predicate claim);
    # 'subject_and_network' passes via a tell (not only network expansion).
    crit = critique(_draft("advisory", "tell"))
    passed = {g.key for g in crit.grades if g.passed}
    assert "why" in passed
    assert "subject_and_network" in passed
    assert "on_chain_evidence" not in passed  # tell alone is not on-chain evidence


def test_gaps_order_is_required_first_then_rubric_order():
    crit = critique(_draft("who"))
    # all remaining required elements, in rubric order (all equal weight/required)
    assert crit.gap_keys() == ["what", "when", "where", "why", "how",
                               "subject_and_network", "on_chain_evidence"]


def test_empty_draft_covers_nothing():
    crit = critique(_draft())
    assert crit.coverage == 0.0
    assert not crit.meets_bar()
    assert len(crit.gaps()) == len(FINCEN_RUBRIC)


def test_critic_config_shape_and_version():
    cfg = critic_config()
    assert cfg["version"] == CRITIC_VERSION
    assert cfg["threshold"] == CRITIC_THRESHOLD
    assert [e["key"] for e in cfg["elements"]] == [e.key for e in FINCEN_RUBRIC]
    assert all("weight" in e and "required" in e for e in cfg["elements"])


def test_critique_is_deterministic():
    d = _draft("who", "what", "network")
    assert critique(d).summary() == critique(d).summary()


def test_summary_is_ascii_and_serializable():
    import json
    s = json.dumps(critique(_draft("who", "network")).summary())
    assert s.isascii()
