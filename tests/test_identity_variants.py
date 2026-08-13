"""Unit tests for the variant-aware name expansion + screen (Phase 8 Part II T1).

Audit-safe: these exercise the identity module directly over constructed inputs;
they touch no scenario data and no sweep chain. The scenario-level recovery eval
(vs ground_truth) is in ``tests/test_identity_eval.py``.
"""

from __future__ import annotations

from rapidfuzz import fuzz

import pytest

from okojo.identity import (
    IDENTITY_VERSION,
    MAX_VARIANT_BUDGET,
    NameVariantBudgetError,
    VARIANT_MATCH_THRESHOLD,
    expand_name_variants,
    identity_config,
    name_variant_budget,
)
from okojo.sweep import NAME_MATCH_THRESHOLD


def test_variant_threshold_pinned_to_direct_screen():
    """The variant layer runs at the same bar as the direct screen it sharpens.
    One separation argument, pinned constants: any divergence must be argued
    through an IDENTITY_VERSION bump, never drift in silently."""
    from okojo.remarks.screening import SCREEN_THRESHOLD

    assert VARIANT_MATCH_THRESHOLD == NAME_MATCH_THRESHOLD == SCREEN_THRESHOLD == 85


def test_identity_version_and_config_shape():
    cfg = identity_config()
    assert cfg["version"] == IDENTITY_VERSION == "1.0.0"
    assert cfg["variant_match_threshold"] == VARIANT_MATCH_THRESHOLD
    assert set(cfg["transliteration_families"]) == {"cyrillic", "arabic"}
    # Reserved surface declared complete for T3/T4 (no later version bump).
    assert cfg["ownership_control_threshold"] == 0.50
    assert len(cfg["proximity_signal_registry"]) == 7


def test_expansion_identity_variant_first_and_empty_path():
    variants = expand_name_variants("Yevgeniy Zhukovskiy")
    # The identity variant (no rule fired) is present and first.
    assert variants[0] == ("yevgeniy zhukovskiy", ())
    # Deterministic + de-duplicated.
    strings = [v for v, _ in variants]
    assert len(strings) == len(set(strings))


def test_expansion_recovers_cross_romanization_form_with_rule_path():
    """A different published romanization is reachable, and the rule path names
    the exact equivalence classes that bridged the gap."""
    variants = dict(expand_name_variants("Yevgeniy Zhukovskiy"))
    assert "evgenii zhukovsky" in variants
    assert variants["evgenii zhukovsky"] == ("cyr-yevgeniy", "cyr-skiy")

    arabic = dict(expand_name_variants("Muhammad Al-Sayigh"))
    assert "mohammed el sayegh" in arabic
    assert arabic["mohammed el sayegh"] == ("ara-muhammad", "ara-article", "ara-sayigh")


def test_direct_screen_misses_but_variant_bridges():
    """The property the layer exists for: the raw WRatio is BELOW threshold (a
    direct-screen miss), while a documented variant scores at or above it."""
    for designated, customer in [
        ("Yevgeniy Zhukovskiy", "Evgenii Zhukovsky"),
        ("Muhammad Al-Sayigh", "Mohammed El-Sayegh"),
    ]:
        raw = fuzz.WRatio(designated, customer)
        assert raw < VARIANT_MATCH_THRESHOLD, (designated, raw)
        cust_norm = customer.lower().replace("-", " ")
        best = max(fuzz.WRatio(v, cust_norm) for v, f in expand_name_variants(designated) if f)
        assert best >= VARIANT_MATCH_THRESHOLD, (designated, best)


def test_inert_on_names_without_romanization_triggers():
    """A name with no token in any equivalence class expands to itself only —
    the layer is inert on ordinary Latin names (so it never perturbs existing
    designations)."""
    variants = expand_name_variants("Bandar Petrochemical Front")
    assert [v for v, _ in variants] == ["bandar petrochemical front"]


def test_variant_budget_counts_the_product_exactly():
    """The budget probe equals the real (pre-dedup) product size, so the value
    the Pydantic boundary checks is the exact work the expander would do."""
    # muhammad(5 forms) x al(3) x sayigh(3) = 45; the expander de-dups to 45 here
    # because no two paths collide, so the probe and the enumeration agree.
    assert name_variant_budget("Muhammad Al-Sayigh") == 45
    assert len(expand_name_variants("Muhammad Al-Sayigh")) == 45
    # An ordinary Latin name has no equivalence-class token: exactly one variant.
    assert name_variant_budget("Bandar Petrochemical Front") == 1


def test_expand_refuses_over_budget_before_enumerating():
    """Defense in depth: even a direct caller of expand_name_variants cannot
    trigger unbounded work — the budget is enforced before any product is built.
    A 3-form article repeated 12 times is 3**12 = 531441 variants, far over
    budget, and the refusal is a fast, clean exception (never an OOM/hang)."""
    exploding = " ".join(["al"] * 12)
    assert name_variant_budget(exploding) > MAX_VARIANT_BUDGET
    with pytest.raises(NameVariantBudgetError):
        expand_name_variants(exploding)


def test_shared_surname_alone_does_not_match():
    """A decoy sharing only the surname (first name OUTSIDE the equivalence
    class) must stay below threshold — discrimination, not over-matching."""
    for designated, decoy in [
        ("Yevgeniy Zhukovskiy", "Dmitri Zhukovsky"),
        ("Muhammad Al-Sayigh", "Khalid El-Sayegh"),
    ]:
        decoy_norm = decoy.lower().replace("-", " ")
        best = max(fuzz.WRatio(v, decoy_norm) for v, f in expand_name_variants(designated) if f)
        assert best < VARIANT_MATCH_THRESHOLD, (designated, decoy, best)
