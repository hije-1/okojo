"""Identity-review RFI — the FIRST subject-facing surface in Phase 8.

When corroboration cannot resolve a name/variant-matched customer either way —
outcome ``possible_match_needs_human`` — the review needs the customer's help to
settle it. This module prepares a **routine identity/document-verification
request** to that customer, drafted for a human to review and send. It is the
sweep's analogue of the case pipeline's follow-up RFI, and it inherits that
discipline verbatim:

* **Anti-tipping-off governs this surface.** The rendered request is validated
  fail-closed by :func:`assert_no_tipping_off`. It may say only what a routine
  records-maintenance letter says; it must NEVER reveal that a designation match
  exists, the screening or corroboration methods, any list source, or any
  investigation or law-enforcement interest. A request that trips the guard is
  **suppressed and surfaced** (flagged for human authoring), never emitted.
* **Grounded + resolvable, fail-closed.** Every draft cites the candidate's own
  KYC identity-attributes row — the record it asks the customer to confirm — and
  that pointer must resolve against the evidence stores before the draft is
  emitted.
* **``drafted_pending_human_review`` is the only representable status.** No send
  path exists in this codebase; a human owns assembly, judgment, and any sending.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..agency import DecisionRecord, TippingOffRisk, assert_no_tipping_off
from ..connectors import Connectors
from ..provenance import Provenance
from ..sar import GroundingResolver
from .designation import Designation

DRAFT_STATUS = "drafted_pending_human_review"

# The outcome that earns an identity-review RFI: corroboration could neither
# confirm nor disqualify the customer, so a human needs the customer's help.
# A corroborated true hit is already resolved (asking would tip off); a
# name-only dismissal is a cleared collision (no customer contact is warranted).
_RFI_TRIGGER_OUTCOME = "possible_match_needs_human"

# Approved neutral template — a routine records-maintenance request built from
# administrative vocabulary only, safe by construction and still validated after
# rendering (defense in depth). It names no list, no match, no method; it asks
# only that the customer confirm the identity details already on file. Deliberate
# word choices dodge the anti-tipping-off bans: "records-maintenance" (not
# "report"), "identity records we hold" (not "registry"/"under review").
_IDENTITY_REVIEW_REQUEST = (
    "Dear {subject_name},\n\n"
    "As part of routine maintenance of our customer identification records, we "
    "are confirming that the identity details we hold for your account are "
    "current and accurate. Please confirm your full legal name, date of birth, "
    "and nationality as they should appear on your file, and provide a clear "
    "copy of a current government-issued identity document. If any of these "
    "details have changed, please provide updated documentation.\n\n"
    "This is a standard records-maintenance request; no action is required on "
    "your account beyond confirming your identity details."
)


class IdentityReviewRfi(BaseModel):
    """One subject-facing identity-verification request, drafted never sent."""

    rfi_id: str
    uid: int
    subject_name: str
    text: str                    # the fully rendered, anti-tipping-off-cleared ask
    status: str = DRAFT_STATUS   # the only status this codebase can produce
    citations: list[str]         # analyst-facing pointers, never part of the text
    provenance: list[Provenance]


class SuppressedIdentityRfi(BaseModel):
    """A draft the fail-closed validator refused to emit — surfaced, with why."""

    uid: int
    reason: str


def draft_identity_review_rfis(
    conn: Connectors,
    designation: Designation,
    corroboration: list[DecisionRecord],
) -> tuple[list[IdentityReviewRfi], list[SuppressedIdentityRfi]]:
    """Draft an identity-review RFI for each ``possible_match_needs_human``
    candidate the corroboration step could not resolve.

    Returns ``(drafts, suppressed)`` — a draft is emitted only if it grounds to
    a resolvable KYC row AND its rendered text clears :func:`assert_no_tipping_off`;
    otherwise it is suppressed and surfaced with a reason, never silently dropped
    and never emitted. Deterministic: candidates are taken in the corroboration
    order (already uid-sorted), so ``rfi_id`` values are stable.
    """
    resolver = GroundingResolver(conn)
    drafts: list[IdentityReviewRfi] = []
    suppressed: list[SuppressedIdentityRfi] = []
    counter = 0

    for rec in corroboration:
        if rec.outcome != _RFI_TRIGGER_OUTCOME:
            continue
        uid = rec.evidence["candidate_uid"]

        # Ground in the candidate's own KYC identity-attributes row — the record
        # the request asks the customer to confirm. Absent row => nothing to
        # ground to => suppress-and-surface.
        kyc_rec = conn.kyc_identity_attributes_for(uid)
        if kyc_rec is None or not resolver.resolves(kyc_rec.provenance):
            suppressed.append(SuppressedIdentityRfi(
                uid=uid,
                reason="no resolvable KYC identity record to ground the request; "
                       "flagged for human authoring",
            ))
            continue

        acct = conn.get_account(uid)
        subject_name = str(acct["entity_name"]) if acct is not None else f"account {uid}"
        text = _IDENTITY_REVIEW_REQUEST.format(subject_name=subject_name)

        # Fail-closed on the fully rendered text (interpolated values are the
        # likeliest smuggling path): a request that could tip the subject off is
        # suppressed and surfaced for human authoring, never emitted.
        try:
            assert_no_tipping_off(text)
        except TippingOffRisk as exc:
            suppressed.append(SuppressedIdentityRfi(
                uid=uid,
                reason=f"anti-tipping-off check failed ({exc}); flagged for human authoring",
            ))
            continue

        counter += 1
        drafts.append(IdentityReviewRfi(
            rfi_id=f"IDR-{designation.designation_id}-{counter:04d}",
            uid=uid,
            subject_name=subject_name,
            text=text,
            citations=[kyc_rec.provenance.cite()],
            provenance=[kyc_rec.provenance],
        ))
    return drafts, suppressed
