"""Geo-action proposals — one REVIEW-tier proposal per surfaced geo dossier
(Phase 8 Part III U2b).

The store-touching wiring between the pure ``decide_geo_action`` decision (the
seventh agency decision) and the sweep: for a TERRITORY designation, each
surfaced :class:`~okojo.geo.GeoDossier` is scored into a proposal from its
totality (signal weight classes minus counter-evidence staleness). The proposal
logic itself lives in ``agency`` (pure); this module only reads the dossier and,
for the one outcome that becomes subject-facing — an enhanced-due-diligence
identity/geography RFI — drafts the ask under the same anti-tipping-off
discipline as the Part-II identity-review RFI.

Discipline (inherited verbatim from the T5 identity-review RFI):

* **``drafted_pending_human_review`` is the only representable status.** No send
  path, no execution path exists. A restriction/block/escalation is *proposed*;
  an RFI is *drafted*; a rebutted signal proposes nothing but the account still
  surfaces with its full dossier (never a silent dismissal).
* **Any subject-facing RFI text is validated fail-closed** by
  :func:`assert_no_tipping_off`, on the fully rendered text, and grounded in the
  customer's own account row (which must resolve against the evidence stores).
  A draft that trips the guard or cannot ground is **suppressed and surfaced**
  with a reason — never emitted, never silently dropped.
* Internal analyst text (the decision rationale) legitimately uses the real
  vocabulary and is out of the validator's scope — the boundary runs between
  audiences, not topics.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..agency import TippingOffRisk, assert_no_tipping_off, decide_geo_action
from ..connectors import Connectors
from ..geo import GeoDossier
from ..provenance import Provenance
from ..sar import GroundingResolver
from .designation import Designation

DRAFT_STATUS = "drafted_pending_human_review"

# The one proposal that becomes a subject-facing draft: an EDD identity/geography
# RFI. The restriction/block/escalation proposals go to the human remediation
# owner (internal), and no_action proposes nothing at all.
_EDD_RFI_OUTCOME = "propose_edd_rfi"

# Neutral EDD RFI template — a routine records-maintenance ask, safe by
# construction and still validated after rendering (defense in depth). It names
# no territory, no match, no method, no list; it asks only that the customer
# confirm the identity and residence details already on file. Word choices dodge
# the anti-tipping-off bans ("records-maintenance", "details we hold").
_EDD_RFI_REQUEST = (
    "Dear {subject_name},\n\n"
    "As part of routine maintenance of our customer records, we are confirming "
    "that the identity and residence details we hold for your account are "
    "current and accurate. Please confirm your full legal name, date of birth, "
    "nationality, and current country of residence as they should appear on your "
    "file, and provide a recent proof-of-residence document (for example a "
    "utility bill or bank statement dated within the last three months). If any "
    "of these details have changed, please provide updated documentation.\n\n"
    "This is a standard records-maintenance request; no action is required on "
    "your account beyond confirming your details."
)


class GeoProposal(BaseModel):
    """One surfaced geo dossier's REVIEW-tier proposal — drafted, never executed.

    ``outcome`` is the ``decide_geo_action`` proposal (from the totality). For
    ``propose_edd_rfi`` and only then, ``rfi_text`` carries the fully rendered,
    anti-tipping-off-cleared subject-facing ask (or ``rfi_suppressed_reason``
    names why it was withheld). ``rationale``/``plain_language`` are the
    analyst-facing decision text and are never put to a subject.
    """

    uid: int
    entity_name: str
    outcome: str
    net_presence_score: int
    rationale: str
    plain_language: str
    status: str = DRAFT_STATUS
    rfi_text: Optional[str] = None
    rfi_suppressed_reason: Optional[str] = None
    citations: list[str]                 # analyst-facing dossier pointers
    provenance: list[Provenance]

    @property
    def is_action(self) -> bool:
        """True iff the proposal recommends any restriction/RFI (i.e. not the
        rebutted ``no_action`` outcome). Used by the UI/roster to show that a
        no_action account is still a resolved review, not a dropped one."""
        return self.outcome != "no_action_totality_resolves"


def build_geo_proposals(
    conn: Connectors,
    designation: Designation,
    dossiers: list[GeoDossier],
) -> list[GeoProposal]:
    """One proposal per surfaced dossier, in the dossiers' (uid) order.

    Pure routing over ``decide_geo_action``: the signal weight classes and the
    counter-evidence staleness statuses are read straight off each dossier. Every
    surfaced account yields a proposal — including ``no_action_totality_resolves``
    (surfaced for review with its full dossier, PM Rider A). Deterministic and
    read-only apart from the grounding membership read."""
    resolver = GroundingResolver(conn)
    out: list[GeoProposal] = []
    for d in dossiers:
        rec = decide_geo_action(
            d.uid,
            [s.weight_class for s in d.signals],
            [c.staleness for c in d.counter_evidence],
            provenance=[p.cite() for p in d.provenance],
        )
        rfi_text: Optional[str] = None
        rfi_suppressed: Optional[str] = None
        if rec.outcome == _EDD_RFI_OUTCOME:
            acct = conn.get_account(d.uid)
            if acct is None or not resolver.resolves(acct.provenance):
                rfi_suppressed = ("no resolvable account record to ground the "
                                  "request; flagged for human authoring")
            else:
                text = _EDD_RFI_REQUEST.format(subject_name=d.entity_name)
                # Fail-closed on the fully rendered text (interpolated values are
                # the likeliest smuggling path).
                try:
                    assert_no_tipping_off(text)
                    rfi_text = text
                except TippingOffRisk as exc:
                    rfi_suppressed = (f"anti-tipping-off check failed ({exc}); "
                                      "flagged for human authoring")
        out.append(GeoProposal(
            uid=d.uid,
            entity_name=d.entity_name,
            outcome=rec.outcome,
            net_presence_score=rec.evidence["net_presence_score"],
            rationale=rec.rationale,
            plain_language=rec.plain_language,
            status=DRAFT_STATUS,
            rfi_text=rfi_text,
            rfi_suppressed_reason=rfi_suppressed,
            citations=[p.cite() for p in d.provenance],
            provenance=list(d.provenance),
        ))
    return out
