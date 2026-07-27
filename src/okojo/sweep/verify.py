"""Block-status verification — two-system sanctions-hold reconciliation.

The data-integrity failure documented in public enforcement actions: the
operational admin system (the system of record) and the analytics warehouse
copy silently disagree about who is on hold, and nobody is comparing them.
The sweep reconciles the FULL tables — every account, both systems — so a gap
anywhere surfaces, not just on accounts the current designation touches.

Read-only, like everything in Okojo: a gap is *flagged with both rows cited*;
no status is ever changed by the sweep.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance

# (warehouse_status, admin_status) -> gap_type for the two planted drift
# directions; identical statuses are consistent, and one-sided rows fall to
# the defensive missing_* types below.
_GAP_TYPES = {
    ("no_hold", "blocked"): "missed_sync_block",
    ("blocked", "no_hold"): "unrecorded_unblock",
}


class StatusGap(BaseModel):
    """One account whose hold status differs between the two systems."""

    uid: int
    warehouse_status: str      # "absent" when the row is missing entirely
    admin_status: str
    gap_type: str
    provenance: list[Provenance]


def verify_block_status(conn: Connectors) -> list[StatusGap]:
    """Reconcile the warehouse and admin hold tables account-by-account.

    Returns every disagreement, ordered by uid, each citing the hold row(s)
    behind it. An empty list means the two systems agree everywhere.
    """
    wh = {int(r["uid"]): r for r in conn.warehouse_holds()}
    adm = {int(r["uid"]): r for r in conn.admin_holds()}

    gaps: list[StatusGap] = []
    for uid in sorted(set(wh) | set(adm)):
        w, a = wh.get(uid), adm.get(uid)
        if w is None:
            gaps.append(StatusGap(
                uid=uid, warehouse_status="absent",
                admin_status=str(a["hold_status"]),
                gap_type="missing_in_warehouse", provenance=[a.provenance],
            ))
        elif a is None:
            gaps.append(StatusGap(
                uid=uid, warehouse_status=str(w["hold_status"]),
                admin_status="absent",
                gap_type="missing_in_admin", provenance=[w.provenance],
            ))
        elif str(w["hold_status"]) != str(a["hold_status"]):
            pair = (str(w["hold_status"]), str(a["hold_status"]))
            gaps.append(StatusGap(
                uid=uid, warehouse_status=pair[0], admin_status=pair[1],
                gap_type=_GAP_TYPES.get(pair, "status_mismatch"),
                provenance=[w.provenance, a.provenance],
            ))
    return gaps
