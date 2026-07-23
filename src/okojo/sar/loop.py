"""Bounded, deterministic SAR drafter-critic revision loop.

The drafter produces a grounded first draft; the Critic grades it against the
FinCEN rubric; the loop then fills the Critic's gaps from evidence already in
hand and re-grades — repeating until the draft clears the bar or a **hard
iteration cap** is hit. Two invariants make this a compliance feature rather than
an open-ended agent:

1. **Deterministic and bounded.** Same inputs -> same iterations -> same output.
   The loop stops the instant a pass adds no new grounded claim (fixpoint) or the
   cap is reached — it can never spin.
2. **Never fabricates.** Revision only re-assembles grounded claims from retrieved
   evidence. Any rubric element the evidence cannot support is left uncovered and
   **flagged for human review** in the filing note — surfaced, not invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..advisory import AdvisoryMatch
from ..aggregator import ProfileTimeline
from ..connectors import Connectors
from ..network import NetworkExpansion
from ..remarks import RemarkTell
from .critic import Critique, critique
from .drafter import build_sar, gap_fill_claims
from .schema import SarDraft, assert_grounded
from .validate import assert_resolvable

# Hard cap on revision passes. The loop reaches a fixpoint well inside this on the
# synthetic scenarios; the cap is the deterministic backstop, not the usual exit.
MAX_REVISION_ITERATIONS = 3


@dataclass
class CritiqueHistory:
    """The full drafter-critic trajectory: a grade per pass + what each pass did."""

    critiques: list[Critique]
    revisions: list[list[str]] = field(default_factory=list)  # elements addressed per pass
    flagged: list[str] = field(default_factory=list)          # left for human review

    @property
    def initial(self) -> Critique:
        return self.critiques[0]

    @property
    def final(self) -> Critique:
        return self.critiques[-1]

    @property
    def iterations(self) -> int:
        """Number of revision passes performed (0 == first draft already cleared)."""
        return len(self.revisions)

    @property
    def converged(self) -> bool:
        return self.final.meets_bar()


def _extend(draft: SarDraft, new_claims: list) -> SarDraft:
    return draft.model_copy(update={"claims": list(draft.claims) + list(new_claims)})


def _human_fallback_note(draft: SarDraft, flagged: list[str]) -> SarDraft:
    note = (
        f"{draft.filing_note} "
        f"CRITIC NOTE: automated revision could not raise the draft to full rubric "
        f"coverage; element(s) flagged for analyst review (not fabricated): "
        f"{', '.join(flagged)}."
    )
    return draft.model_copy(update={"filing_note": note})


def draft_with_critic(
    conn: Connectors,
    profile: ProfileTimeline,
    expansion: NetworkExpansion,
    tells: list[RemarkTell],
    advisory: Optional[AdvisoryMatch],
    max_iterations: int = MAX_REVISION_ITERATIONS,
) -> tuple[SarDraft, CritiqueHistory]:
    """Draft, critique, and revise within a deterministic bound.

    Returns the (possibly revised) draft and the full :class:`CritiqueHistory`.
    """
    draft = build_sar(conn, profile, expansion, tells, advisory)  # grounded + validated
    critiques = [critique(draft)]
    revisions: list[list[str]] = []

    while len(revisions) < max_iterations and not critiques[-1].meets_bar():
        gaps = critiques[-1].gap_keys()
        new_claims = gap_fill_claims(conn, profile, expansion, advisory, gaps)
        if not new_claims:
            break  # no fillable gap remains -> stop (fixpoint); residue is flagged below
        draft = _extend(draft, new_claims)
        # Every revised draft re-passes the full grounding contract, fail-closed.
        assert_grounded(draft)
        assert_resolvable(conn, draft)
        crit = critique(draft)
        revisions.append([c.element for c in new_claims])
        critiques.append(crit)

    flagged = [] if critiques[-1].meets_bar() else critiques[-1].gap_keys()
    if flagged:
        draft = _human_fallback_note(draft, flagged)

    return draft, CritiqueHistory(critiques=critiques, revisions=revisions, flagged=flagged)
