"""Beneficial-owner + officer walk (Phase 8 Part II T3).

Given a *resolved* designated party (a customer the name/variant screen matched
and corroboration did not dismiss), walk the synthetic KYB ownership and officer
structure around it and surface three REVIEW-tier findings:

* **ownership propagation** — a company at or above ``OWNERSHIP_CONTROL_THRESHOLD``
  owned by the designated party is surfaced as *owned/controlled by a designated
  party*; below the threshold it is not;
* **fictitious executive** — an officer of record with **no resolvable identity
  footprint** (a name-only appointment whose name matches no account and no KYC
  holder) is flagged;
* **post-designation control change** — an officer appointment (or ownership
  record) dated **after** the designation is flagged as a control change that
  postdates the designation event.

Ownership and officer edges are a **DISTINCT edge type**: exactly like a
gas-funding edge, they can never fabricate on-chain flow exposure. This module
returns review findings and their provenance only — it never touches the
exposure walk, and a test asserts the propagation adds zero USDT.

Everything here is calibrated and REVIEW-tier: the walk *surfaces* and
*proposes*; a human resolves. Deterministic and RNG-free.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance
from . import OWNERSHIP_CONTROL_THRESHOLD


def _norm_name(name: str) -> str:
    """Whitespace/case-normalised name — the identity-footprint comparison form."""
    return " ".join(str(name).lower().split())


def _as_float(value) -> float:
    """An ownership fraction as a float, robust to the CSV round-trip."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class OwnershipPropagation(BaseModel):
    """A company owned at or above the control threshold by a designated party."""

    company_uid: int
    company_name: str
    owner_uid: int
    ownership_pct: float
    provenance: list[Provenance]


class FictitiousExecutiveFlag(BaseModel):
    """A name-only officer of record with no resolvable identity footprint."""

    appointment_id: str
    company_uid: int
    officer_name: str
    provenance: list[Provenance]


class ControlChangeFlag(BaseModel):
    """An officer/ownership change dated after the designation event."""

    appointment_id: str
    company_uid: int
    officer_name: str
    changed_date: str
    designation_date: str
    provenance: list[Provenance]


class OwnershipWalkResult(BaseModel):
    """The three REVIEW-tier findings of one ownership/officer walk."""

    propagations: list[OwnershipPropagation] = []
    fictitious_executives: list[FictitiousExecutiveFlag] = []
    control_changes: list[ControlChangeFlag] = []

    def is_empty(self) -> bool:
        return not (self.propagations or self.fictitious_executives
                    or self.control_changes)

    def exposure_usdt(self) -> float:
        """Ownership/officer edges are a distinct edge type: they NEVER carry
        flow exposure. This is always 0.0 by construction — asserted by test."""
        return 0.0


def _identity_footprint(conn: Connectors) -> set[str]:
    """The set of normalised names that resolve to a real identity — every
    account entity_name and every KYC holder_name. An officer whose name is not
    in this set (and whose uid resolves to no account) has no footprint."""
    names = {_norm_name(a["entity_name"]) for a in conn.all_accounts()}
    names |= {_norm_name(k["holder_name"]) for k in conn.all_kyc()}
    return names


def _has_footprint(conn: Connectors, footprint: set[str],
                   account_uids: set[int], officer_uid: str,
                   officer_name: str) -> bool:
    """True iff this officer resolves to a real identity: a uid naming an
    account, or a name matching an account/KYC holder."""
    uid = str(officer_uid).strip()
    if uid and uid.lower() != "nan":
        try:
            if int(float(uid)) in account_uids:
                return True
        except (TypeError, ValueError):
            pass
    return _norm_name(officer_name) in footprint


def walk_ownership(conn: Connectors, resolved_party_uids: list[int],
                   designation_date: str) -> OwnershipWalkResult:
    """Walk the ownership/officer structure around the resolved designated
    party/parties and surface the three REVIEW-tier findings.

    ``resolved_party_uids`` are the customers the name/variant screen matched and
    corroboration did not dismiss — a party dismissed as a same-name collision
    seeds no walk. Companies of interest are those a resolved party beneficially
    owns (at any stake); designation status propagates only to those at or above
    the control threshold, while the fictitious-executive and control-change
    detectors run over the officers of those companies. Deterministic: findings
    are ordered by company/appointment id.
    """
    result = OwnershipWalkResult()
    if not resolved_party_uids:
        return result
    parties = set(resolved_party_uids)

    accounts = {int(a["uid"]): a for a in conn.all_accounts()}
    account_uids = set(accounts)

    # Companies a resolved party owns (at any stake) — the walk's scope.
    companies_of_interest: set[int] = set()
    for rec in conn.beneficial_ownership():
        if int(rec["owner_uid"]) in parties:
            company_uid = int(rec["company_uid"])
            companies_of_interest.add(company_uid)
            pct = _as_float(rec["ownership_pct"])
            if pct >= OWNERSHIP_CONTROL_THRESHOLD:
                acct = accounts.get(company_uid)
                result.propagations.append(OwnershipPropagation(
                    company_uid=company_uid,
                    company_name=str(acct["entity_name"]) if acct else "",
                    owner_uid=int(rec["owner_uid"]),
                    ownership_pct=pct,
                    provenance=[rec.provenance]
                    + ([acct.provenance] if acct else []),
                ))
            # An ownership record dated after the designation is itself a
            # control-change signal (a stake acquired post-designation).
            if str(rec["as_of_date"]) > designation_date:
                acct = accounts.get(company_uid)
                result.control_changes.append(ControlChangeFlag(
                    appointment_id=f"ownership:owner:{rec['owner_uid']}:company:{company_uid}",
                    company_uid=company_uid,
                    officer_name=str(acct["entity_name"]) if acct else "",
                    changed_date=str(rec["as_of_date"]),
                    designation_date=designation_date,
                    provenance=[rec.provenance],
                ))
    result.propagations.sort(key=lambda p: p.company_uid)

    # Officers of the companies of interest: fictitious-executive + control-change.
    footprint = _identity_footprint(conn)
    for rec in conn.officer_appointments():
        company_uid = int(rec["company_uid"])
        if company_uid not in companies_of_interest:
            continue
        appt_id = str(rec["appointment_id"])
        officer_uid = "" if rec["officer_uid"] is None else str(rec["officer_uid"])
        officer_name = "" if rec["officer_name"] is None else str(rec["officer_name"])
        name_only = not officer_uid.strip() or officer_uid.strip().lower() == "nan"
        if name_only and not _has_footprint(conn, footprint, account_uids, "", officer_name):
            result.fictitious_executives.append(FictitiousExecutiveFlag(
                appointment_id=appt_id, company_uid=company_uid,
                officer_name=officer_name, provenance=[rec.provenance],
            ))
        if str(rec["appointed_date"]) > designation_date:
            result.control_changes.append(ControlChangeFlag(
                appointment_id=appt_id, company_uid=company_uid,
                officer_name=officer_name, changed_date=str(rec["appointed_date"]),
                designation_date=designation_date, provenance=[rec.provenance],
            ))
    result.fictitious_executives.sort(key=lambda f: f.appointment_id)
    result.control_changes.sort(key=lambda c: c.appointment_id)
    return result
