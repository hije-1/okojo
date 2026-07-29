"""Proximity ring (Phase 8 Part II T4).

Surface the relatives and close associates of a *resolved* designated party for
**REVIEW** — never as exposure, and never as asserted kinship. Kinship is a
**correlational signal the system surfaces with its evidence**; a human decides.
Every ring statement stays in calibrated language (*candidate* / *possible* /
*shares*), never "is the sister of".

Signals (the reserved ``PROXIMITY_SIGNAL_REGISTRY`` from T1, consumed here with
no version bump):

* **primary** (surface a candidate into the ring): a shared surname/patronymic
  token, declared-relationship metadata on file, a relationship-asserting remark,
  or a KYC-document cross-holding (one party's identity document inside another's
  account);
* **weighting** (add evidence to an already-surfaced candidate, never surface one
  alone — the packet's "shared surname *weighted by* shared KYC attributes"): a
  shared KYC attribute (address / contact) or a shared email-handle pattern.
  Non-distinctive placeholder values are ignored, so they can never fabricate a
  weight.

**Not weighted by activity volume** — dormancy is not innocence: a dormant,
densely-linked account surfaces exactly as loudly as an active one. The
**shared-device** signal in the registry is deliberately *not* re-evaluated here:
device linkage is already surfaced by the sweep's exposure/adjacency walk, and
the proximity layer adds the kinship signals it does not cover. Accounts already
surfaced as exposed or adjacent are excluded, so the ring is the *otherwise-
unconnected* associates. Deterministic and RNG-free.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance

# A KYC attribute equal to one of these non-distinctive placeholders carries no
# weight — it is shared by construction across same-nationality synthetic
# subjects, so treating it as a match would fabricate a signal (the corroboration
# "absent field is UNKNOWN" discipline, applied to weighting).
_PLACEHOLDER_ADDRESS = re.compile(r"\(synthetic address on file\)\s*$", re.I)
_PLACEHOLDER_EMAIL = re.compile(r"^subject\d+@example\.invalid$", re.I)


def _surname(name: str) -> str:
    """The surname/patronymic token — the last whitespace token, normalised."""
    toks = [t for t in str(name).replace("-", " ").split() if t]
    return toks[-1].strip(".,'").lower() if toks else ""


def _email_handle(email: str) -> str:
    """The distinctive local-part of an email, or "" for a placeholder."""
    e = str(email).strip()
    if not e or _PLACEHOLDER_EMAIL.match(e):
        return ""
    return e.split("@", 1)[0].lower()


def _distinct_address(address: str) -> str:
    """A distinctive address string, or "" for a non-distinctive placeholder."""
    a = str(address).strip()
    if not a or _PLACEHOLDER_ADDRESS.search(a):
        return ""
    return a.lower()


class ProximitySignal(BaseModel):
    signal_id: str
    detail: str
    provenance: Provenance


class ProximityRingMember(BaseModel):
    """One candidate associate of a resolved designated party, surfaced for
    REVIEW with the signals (and their evidence) that placed it in the ring."""

    uid: int
    entity_name: str
    related_party_uid: int
    account_status: str            # carried to SHOW dormancy is not weighted
    primary_signals: list[ProximitySignal]
    weighting_signals: list[ProximitySignal]
    note: str                      # calibrated; never asserts kinship as fact

    @property
    def provenance(self) -> list[Provenance]:
        return [s.provenance for s in (self.primary_signals + self.weighting_signals)]


class ProximityRing(BaseModel):
    members: list[ProximityRingMember] = []

    def is_empty(self) -> bool:
        return not self.members

    def member_uids(self) -> list[int]:
        return sorted(m.uid for m in self.members)

    def exposure_usdt(self) -> float:
        """REVIEW-tier, never exposure: the proximity ring carries no flow
        exposure — always 0.0 by construction (asserted by test)."""
        return 0.0


def build_proximity_ring(conn: Connectors, party_uids: list[int],
                         exclude_uids: Optional[set[int]] = None) -> ProximityRing:
    """Surface the review-tier proximity ring around the resolved party/parties.

    ``party_uids`` are the resolved designated parties (individuals); a candidate
    joins the ring iff it shares at least one PRIMARY signal with a party.
    ``exclude_uids`` (typically the sweep's exposed + adjacent accounts) are
    already surfaced elsewhere and never appear in the ring. Deterministic: ring
    members are ordered by uid, signals in registry order.
    """
    parties = [p for p in party_uids]
    if not parties:
        return ProximityRing()
    exclude = set(exclude_uids or set()) | set(parties)

    accounts = {int(a["uid"]): a for a in conn.all_accounts()}
    kyc = {int(r["uid"]): r for r in conn.kyc_identity_attributes()}
    rels = list(conn.relationships())
    assertions = list(conn.relationship_assertions())

    party_info = {}
    for p in parties:
        acct = accounts.get(p)
        if acct is None:
            continue
        party_info[p] = {
            "surname": _surname(acct["entity_name"]),
            "address": _distinct_address(kyc[p]["address"]) if p in kyc else "",
            "email": _email_handle(kyc[p]["email"]) if p in kyc else "",
        }

    members: list[ProximityRingMember] = []
    for uid, acct in accounts.items():
        if uid in exclude:
            continue
        for party in parties:
            pinfo = party_info.get(party)
            if pinfo is None:
                continue
            primary: list[ProximitySignal] = []
            weighting: list[ProximitySignal] = []

            # -- PRIMARY: shared surname/patronymic --------------------------
            cand_surname = _surname(acct["entity_name"])
            if cand_surname and cand_surname == pinfo["surname"]:
                primary.append(ProximitySignal(
                    signal_id="shared_surname",
                    detail=f"shares the surname/patronymic token '{cand_surname}' "
                           "with the resolved party",
                    provenance=acct.provenance,
                ))

            # -- PRIMARY: declared-relationship metadata ---------------------
            for r in rels:
                pair = {int(r["uid_a"]), int(r["uid_b"])}
                if pair == {uid, party}:
                    primary.append(ProximitySignal(
                        signal_id="declared_relationship",
                        detail=f"a declared '{r['declared_relationship']}' "
                               "relationship is on file",
                        provenance=r.provenance,
                    ))

            # -- PRIMARY: relationship remark / KYC-document cross-holding ----
            for a in assertions:
                pair = {int(a["subject_uid"]), int(a["related_uid"])}
                if pair != {uid, party}:
                    continue
                atype = str(a["assertion_type"])
                if atype in ("relationship_remark", "kyc_document_cross_holding"):
                    primary.append(ProximitySignal(
                        signal_id=atype, detail=str(a["detail"]),
                        provenance=a.provenance,
                    ))

            if not primary:
                continue

            # -- WEIGHTING: shared KYC attribute / email handle (evidence only)
            cand_kyc = kyc.get(uid)
            if cand_kyc is not None:
                addr = _distinct_address(cand_kyc["address"])
                if addr and addr == pinfo["address"]:
                    weighting.append(ProximitySignal(
                        signal_id="shared_kyc_attribute",
                        detail="shares a KYC address on file with the resolved party",
                        provenance=cand_kyc.provenance,
                    ))
                handle = _email_handle(cand_kyc["email"])
                if handle and handle == pinfo["email"]:
                    weighting.append(ProximitySignal(
                        signal_id="email_handle_pattern",
                        detail="shares an email-handle pattern with the resolved party",
                        provenance=cand_kyc.provenance,
                    ))

            sig_ids = ", ".join(s.signal_id for s in primary)
            members.append(ProximityRingMember(
                uid=uid, entity_name=str(acct["entity_name"]),
                related_party_uid=party,
                account_status=str(acct["account_status"]),
                primary_signals=primary, weighting_signals=weighting,
                note=(f"Candidate associate of the resolved designated party: {sig_ids}. "
                      "Surfaced for review as a possible relative/associate — a "
                      "correlational signal, not an assertion of kinship; a human "
                      "resolves. Surfacing is independent of account activity "
                      "(dormancy is not weighted)."),
            ))
            break  # one membership record per candidate (first related party)

    members.sort(key=lambda m: m.uid)
    return ProximityRing(members=members)
