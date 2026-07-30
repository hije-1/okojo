"""Counterparty-designation lifecycle (Part IV) — what happens AFTER detection.

Detection is already built: the Part I flow sweep surfaces the customers who
dealt with a designated counterparty's addresses, and the S3 ``exposure_timing``
flag already splits pre- from post-designation dealing. This module adds the
relationship lifecycle for a designated counterparty **service** (a VASP /
exchange, the ``counterparty_service`` designation kind):

* a **customer notification** (subject-facing, a Terms-and-Conditions matter)
  drafted for each post-designation dealer — grounded in the customer's own
  account row, authored guard-safe and still validated fail-closed by
  :func:`assert_no_tipping_off`, ``drafted_pending_human_review`` only, **no send
  path**, suppress-and-surface on any failure; and
* the **record-only lifecycle state** each relationship has reached
  (``exposure_detected`` -> ``notification_drafted`` -> ``acknowledgment_recorded``
  -> ``stop_dealing_verified`` -> ``unblock_proposed``, with ``offboard_proposed``
  the divergent terminal for a repeat offender), derived from evidence.

The relationship DISPOSITION itself — propose_unblock / propose_offboard /
hold_pending — is the eighth bounded agency decision
(:func:`okojo.agency.decide_counterparty_lifecycle`); this module supplies the
grounded evidence that decision consumes and the subject-facing surface.

**The hard rule of this part — no auto-unblock.** Nothing here mutates a hold.
Unblock exists ONLY as a proposal record; a human decides and acts. A guard test
proves the pipeline cannot write to either sanctions-hold table.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..agency import DecisionRecord, TippingOffRisk, assert_no_tipping_off
from ..connectors import Connectors, Record
from ..provenance import Provenance
from ..sar import GroundingResolver
from .designation import Designation

DRAFT_STATUS = "drafted_pending_human_review"

# The linear happy-path lifecycle milestones, weakest first. A relationship
# reaches the furthest milestone its evidence supports; the proposal
# (unblock/offboard/hold) is the agency decision layered on top.
LIFECYCLE_STATES: tuple[str, ...] = (
    "exposure_detected",
    "notification_drafted",
    "acknowledgment_recorded",
    "stop_dealing_verified",
    "unblock_proposed",
)
# Divergent terminal: a repeat offender leaves the happy path (recidivism
# dominates an acknowledged-and-stopped relationship — see the agency policy).
LIFECYCLE_OFFBOARD_TERMINAL = "offboard_proposed"


def _tx_date(row) -> str:
    """The ISO date (YYYY-MM-DD) of a transaction row, robust to the CSV
    round-trip. Accepts a connector ``Record`` or a plain mapping (test
    fixtures), so the pure timing helpers are unit-testable without a store."""
    return str(row["timestamp"])[:10]


def counterparty_dealings(conn: Connectors, designation: Designation,
                          uid: int) -> list[Record]:
    """The customer's transactions touching the designated counterparty's
    addresses — the grounded basis for post-designation timing and the verified
    stop. A dealing is a transaction between the customer's cluster (its uid or a
    wallet it controls) and any designated address, in either direction. Ordered
    by ``tx_id`` for determinism; each row carries its own provenance."""
    designated = set(designation.designated_addresses)
    cluster = {f"uid:{uid}"}
    for rec in conn.addresses_for(uid):
        cluster.add(str(rec["address"]))
    out: list[Record] = []
    for t in conn.all_transactions():
        frm, to = str(t["from_ref"]), str(t["to_ref"])
        if (frm in cluster and to in designated) or (to in cluster and frm in designated):
            out.append(t)
    return sorted(out, key=lambda r: str(r["tx_id"]))


def has_post_designation_dealing(dealings, designation_date: str) -> bool:
    """True iff any dealing with the counterparty is dated AFTER the designation
    date — the fact that earns a customer notification (a post-designation
    dealer). Pure over the dealings list."""
    return any(_tx_date(t) > designation_date for t in dealings)


def is_stop_verified(dealings, acknowledged_date: str) -> bool:
    """True iff NO dealing with the counterparty is dated after the
    acknowledgment date — a verified stop (Q6: the cut is the acknowledgment
    date, not the designation date; pre-acknowledgment dealing is what the
    notification addresses and does not bar unblock). Pure over the dealings
    list. An absent acknowledgment date is passed as ``""`` by the caller only
    when the customer never acknowledged, in which case a verified stop is not
    evaluated (the disposition is hold_pending regardless)."""
    return not any(_tx_date(t) > acknowledged_date for t in dealings)


def derive_counterparty_lifecycle_state(*, notification_drafted: bool,
                                        acknowledged: bool, stop_verified: bool,
                                        outcome: str) -> str:
    """The furthest lifecycle milestone a relationship has reached.

    The proposal terminals win (``offboard_proposed`` / ``unblock_proposed``);
    otherwise the state is the furthest EVIDENCE milestone — a recorded
    acknowledgment, a drafted notification, or the bare detected exposure. Pure.
    """
    if outcome == "propose_offboard":
        return LIFECYCLE_OFFBOARD_TERMINAL
    if outcome == "propose_unblock":
        return "unblock_proposed"
    # hold_pending: report how far the evidence got.
    if acknowledged and stop_verified:
        return "stop_dealing_verified"
    if acknowledged:
        return "acknowledgment_recorded"
    if notification_drafted:
        return "notification_drafted"
    return "exposure_detected"


# --- customer notification (subject-facing, T&C matter) ----------------------

# Approved neutral template — a Terms-and-Conditions notification, authored
# guard-safe. Its widened-but-bounded sayable scope (Q4): the counterparty's
# PUBLIC designation and the customer's contractual obligation ARE sayable; the
# evidence methods, the existence of any investigation, and law-enforcement
# interest are NOT. Deliberate word choices are MORE calibrated, not a
# workaround — "designated / listed counterparty", "under the Terms", "may apply
# restrictions" (never "sanctioned" / "blocked" / "frozen" / "reported"). Still
# validated fail-closed after rendering (defense in depth).
_NOTIFICATION = (
    "Dear {subject_name},\n\n"
    "We are writing about {counterparty_name}, which our records indicate your "
    "account has dealt with. {counterparty_name} has been added to a public "
    "designation list. Under the Terms and Conditions of your account, we are "
    "required to conduct a periodic review of dealings connected to designated "
    "counterparties, and we may apply restrictions to your account while that "
    "review is completed.\n\n"
    "Please contact our customer team to discuss the status of your account. "
    "Beyond getting in touch, no further action is required from you at this "
    "time."
)


def render_counterparty_notification(subject_name: str, counterparty_name: str) -> str:
    """Render the notification text — the pure template step, separated so the
    guard-safe property is unit-testable without a store."""
    return _NOTIFICATION.format(subject_name=subject_name,
                                counterparty_name=counterparty_name)


class CounterpartyNotification(BaseModel):
    """One subject-facing counterparty notification, drafted never sent."""

    notification_id: str
    uid: int
    subject_name: str
    counterparty_name: str
    text: str                    # fully rendered, anti-tipping-off-cleared
    status: str = DRAFT_STATUS   # the only status this codebase can produce
    citations: list[str]         # analyst-facing pointers, never part of the text
    provenance: list[Provenance]


class SuppressedNotification(BaseModel):
    """A draft the fail-closed validator (or grounding) refused — surfaced, why."""

    uid: int
    reason: str


def draft_counterparty_notifications(
    conn: Connectors,
    designation: Designation,
    post_designation_uids: list[int],
) -> tuple[list[CounterpartyNotification], list[SuppressedNotification]]:
    """Draft a customer notification for each post-designation-dealing customer.

    Returns ``(drafts, suppressed)`` — a draft is emitted only if it grounds to
    a resolvable account row AND its rendered text clears
    :func:`assert_no_tipping_off`; otherwise it is suppressed and surfaced with a
    reason, never silently dropped and never emitted. Deterministic: uids are
    taken in sorted order, so ``notification_id`` values are stable.
    """
    resolver = GroundingResolver(conn)
    drafts: list[CounterpartyNotification] = []
    suppressed: list[SuppressedNotification] = []
    counter = 0

    for uid in sorted(post_designation_uids):
        acct = conn.get_account(uid)
        if acct is None or not resolver.resolves(acct.provenance):
            suppressed.append(SuppressedNotification(
                uid=uid,
                reason="no resolvable account row to ground the notification; "
                       "flagged for human authoring",
            ))
            continue

        subject_name = str(acct["entity_name"])
        text = render_counterparty_notification(subject_name, designation.designated_name)

        # Fail-closed on the fully rendered text (interpolated values — the
        # subject name and the counterparty name — are the likeliest smuggling
        # path): a notification that could tip the subject off is suppressed and
        # surfaced for human authoring, never emitted.
        try:
            assert_no_tipping_off(text)
        except TippingOffRisk as exc:
            suppressed.append(SuppressedNotification(
                uid=uid,
                reason=f"anti-tipping-off check failed ({exc}); flagged for human authoring",
            ))
            continue

        counter += 1
        drafts.append(CounterpartyNotification(
            notification_id=f"CPN-{designation.designation_id}-{counter:04d}",
            uid=uid,
            subject_name=subject_name,
            counterparty_name=designation.designated_name,
            text=text,
            citations=[acct.provenance.cite()],
            provenance=[acct.provenance],
        ))
    return drafts, suppressed


# --- lifecycle disposition (the record the wiring stamps) --------------------


class LifecycleDisposition(BaseModel):
    """One post-designation-exposed customer's relationship disposition.

    Bundles the derived lifecycle ``state``, the eighth agency ``decision``
    (propose_unblock / propose_offboard / hold_pending), and the three evidence
    booleans that drove it, with provenance for the audit stamp. Record-only —
    no hold is mutated; every proposal is for a human.
    """

    uid: int
    state: str
    outcome: str
    acknowledged: bool
    stop_verified: bool
    repeat_offender: bool
    prior_acknowledged_counterparties: list[str]
    decision: DecisionRecord
    provenance: list[Provenance]
