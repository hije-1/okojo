"""SAR Critic — a deterministic grader against an operationalized FinCEN rubric.

FinCEN asks a SAR narrative to answer *who / what / when / where / why / how*,
identify the **predicate offense**, characterize the **subject and network**, and
(for a crypto matter) marshal **on-chain evidence**. The Critic operationalizes
that expectation as a fixed rubric and grades a :class:`~okojo.sar.schema.SarDraft`
against it — a pure function of the structured claims, no LLM, fully
deterministic and reproducible.

The Critic *grades and surfaces gaps*; it never fabricates evidence to close one.
The bounded revision loop (:mod:`okojo.sar.loop`) acts on the gap list by
re-assembling grounded claims from evidence already in hand, and flags anything
that stays uncovered for human review.

Design: each rubric element maps to the claim ``element`` tags that satisfy it.
An element **passes** iff the draft carries at least one claim with a mapped tag.
Coverage is the weighted fraction of elements passing. Weights, the pass
threshold, and the rubric itself are **tunable policy parameters** — versioned via
:data:`CRITIC_VERSION`, stamped into the audit trail, and mirrored (regression
-tested) by ``docs/sar-critic-methodology.md`` so code and doc never drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import SarDraft


@dataclass(frozen=True)
class RubricElement:
    """One graded expectation. ``claim_elements`` are the claim ``element`` tags
    whose presence satisfies it (any one suffices)."""

    key: str
    label: str
    weight: float
    required: bool
    claim_elements: tuple[str, ...]


# The operationalized FinCEN narrative rubric. Weights are equal pending
# calibration (documented as a policy parameter). ``why`` is satisfied by either
# an explicit predicate-offense claim or a matched regulatory advisory;
# ``subject_and_network`` by network expansion or an attribution tell; and
# ``on_chain_evidence`` by network sanctioned-exposure or an explicit on-chain
# claim. All are required for a draft to clear without human review.
FINCEN_RUBRIC: tuple[RubricElement, ...] = (
    RubricElement("who", "Subject identity (who)", 1.0, True, ("who",)),
    RubricElement("what", "Suspicious activity (what)", 1.0, True, ("what",)),
    RubricElement("when", "Activity timeframe (when)", 1.0, True, ("when",)),
    RubricElement("where", "Jurisdiction / geography (where)", 1.0, True, ("where",)),
    RubricElement("why", "Predicate offense / regulatory basis (why)", 1.0, True, ("predicate", "advisory")),
    RubricElement("how", "Mechanism / methodology (how)", 1.0, True, ("how",)),
    RubricElement("subject_and_network", "Subject-and-network characterization", 1.0, True, ("network", "tell")),
    RubricElement("on_chain_evidence", "On-chain evidence", 1.0, True, ("network", "onchain")),
)

# A draft must cover this weighted fraction of the rubric (and every *required*
# element) to clear the Critic without human-review escalation. 1.0 == every
# rubric element must be present; anything less is flagged for a human.
CRITIC_THRESHOLD = 1.0

# Version of this critic methodology. Bump on any change to the rubric, a weight,
# or the threshold; the config is stamped into the audit trail and mirrored (+
# regression-tested) by ``docs/sar-critic-methodology.md``.
CRITIC_VERSION = "1.0.0"


def critic_config() -> dict:
    """The full, versioned Critic configuration — the tunable *policy parameters*
    behind every grade. Single source of truth: stamped into the audit trail and
    regression-tested against the published methodology doc."""
    return {
        "version": CRITIC_VERSION,
        "threshold": CRITIC_THRESHOLD,
        "elements": [
            {"key": e.key, "weight": e.weight, "required": e.required}
            for e in FINCEN_RUBRIC
        ],
    }


@dataclass(frozen=True)
class ElementGrade:
    """Per-rubric-element outcome for one draft."""

    key: str
    label: str
    weight: float
    required: bool
    passed: bool


@dataclass(frozen=True)
class Critique:
    """A graded draft: per-element outcomes, weighted coverage, and the gap list."""

    version: str
    coverage: float
    threshold: float
    grades: tuple[ElementGrade, ...]

    def gaps(self) -> list[ElementGrade]:
        """Failing elements, required-first then heaviest-first (stable within)."""
        failing = [g for g in self.grades if not g.passed]
        return sorted(failing, key=lambda g: (not g.required, -g.weight))

    def gap_keys(self) -> list[str]:
        return [g.key for g in self.gaps()]

    def meets_bar(self) -> bool:
        """True iff every required element passes and coverage clears threshold."""
        required_ok = all(g.passed for g in self.grades if g.required)
        return required_ok and self.coverage >= self.threshold

    def summary(self) -> dict:
        """Compact, ASCII, audit-loggable summary."""
        return {
            "version": self.version,
            "coverage": round(self.coverage, 3),
            "threshold": self.threshold,
            "meets_bar": self.meets_bar(),
            "gaps": self.gap_keys(),
        }


def critique(draft: SarDraft) -> Critique:
    """Grade a draft against :data:`FINCEN_RUBRIC` — deterministic, no side effects."""
    present = {c.element for c in draft.claims}
    grades = tuple(
        ElementGrade(
            key=e.key, label=e.label, weight=e.weight, required=e.required,
            passed=bool(present.intersection(e.claim_elements)),
        )
        for e in FINCEN_RUBRIC
    )
    total_w = sum(e.weight for e in FINCEN_RUBRIC)
    got_w = sum(g.weight for g in grades if g.passed)
    coverage = got_w / total_w if total_w else 1.0
    return Critique(
        version=CRITIC_VERSION, coverage=coverage, threshold=CRITIC_THRESHOLD, grades=grades,
    )
