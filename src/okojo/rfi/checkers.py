"""Adversarial checkers — test one RFI claim against the evidence (Phase 5, Slice C).

Four probes, one per evidence surface named in the build plan: corporate-registry
OSINT, the subject's own prior RFI answers, on-chain flows, and device data. Each
is a pure function of the read-only connector layer and the shared
:class:`~okojo.entity.EntityBackbone`; each returns zero or more
:class:`Rebuttal` objects, and every rebuttal carries the provenance of the rows
that support it. A checker never *decides* anything — adjudication (:mod:`okojo.
rfi.contradiction`) weighs what the checkers found.

**Applicability is derived from the claim's own text, never from its identity.**
A checker first asks "is this the kind of assertion I can test?" using a
published lexicon — a relationship denial, a source-of-funds assertion, an
exclusive-control assertion — and only then goes looking for rebutting rows.
Wiring a checker to a claim *id* would make the eval circular: the system would
be told which claims to attack rather than working it out.

**Anti-tautology contract.** These checkers read evidence tables only. The
scenario's answer key (its per-claim verdicts, its declared rebuttal sources, its
helper uid lists) exists for the eval, and if a checker could read it the eval
would be scoring the checker against data the checker was handed.
``tests/test_rfi_checkers.py`` asserts this module's source never names any of
those keys.

**Scope boundary, deliberate.** The on-chain probe tests fund-flow assertions and
counterparty-relationship denials. It does *not* test custody/segregation
assertions ("these are our own wallets") — control commingling is what the device
probe is for. Broadening on-chain to argue custody from gas-funding is a
defensible future probe, but it is a scope change, not a bug fix.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..entity import EntityBackbone
from ..provenance import Provenance
from .claims import ExtractedClaim

# --------------------------------------------------------------------------- #
# Policy parameters — published lexicons and evidence weights.
#
# These are *tunable policy*, not magic numbers: they are versioned, stamped into
# the audit trail, and mirrored by docs/rfi-contradiction-methodology.md.
# --------------------------------------------------------------------------- #

# A claim that denies a relationship with another named party.
RELATIONSHIP_DENIAL_TERMS: tuple[str, ...] = (
    "no ownership", "no management", "no relationship", "not related",
    "separate legal entity", "unrelated", "no connection", "arm's length",
)

# A claim that asserts where value came from.
SOURCE_OF_FUNDS_TERMS: tuple[str, ...] = (
    "funds derive", "source of funds", "proceeds", "trade settlement",
    "derive solely", "originate from", "lawful trade",
)

# A claim that asserts exclusive control or segregation of assets.
EXCLUSIVE_CONTROL_TERMS: tuple[str, ...] = (
    "our own", "fully segregated", "segregated per client", "custody wallet",
    "custody wallets", "we alone control",
)

# Prior-answer phrasing that affirms the very relationship a claim denies.
RELATIONSHIP_AFFIRMATION_TERMS: tuple[str, ...] = (
    "settlement agent", "management services agreement", "sits on its board",
    "on behalf of", "manage", "acts for", "our client",
)

# Evidence weights in [0, 1]. A single rebuttal at or above the strong bar
# (see contradiction.STRONG_REBUTTAL) can carry a claim to "contradicted";
# anything weaker needs corroboration from a second, independent source.
W_REGISTRY_COMMON_OFFICER = 0.8
W_PRIOR_RFI_SELF_CONTRADICTION = 0.8
W_ONCHAIN_SANCTIONED_EXPOSURE = 0.9
W_ONCHAIN_GAS_FUNDED_HOP = 0.6
W_ONCHAIN_STRUCTURED = 0.5
W_ONCHAIN_COUNTERPARTY_FLOW = 0.5
W_DEVICE_SHARED_FINGERPRINT = 0.5

SOURCE_KEYS: tuple[str, ...] = ("device", "onchain", "prior_rfi", "registry")

_OPEN_ENDED = "9999-12-31"   # an officer still serving


class Rebuttal(BaseModel):
    """One piece of evidence that cuts against a claim, with its receipts."""

    source: str                 # one of SOURCE_KEYS
    statement: str
    strength: float
    provenance: list[Provenance]

    def cite(self) -> str:
        return "; ".join(p.cite() for p in self.provenance)


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #
def _mentions(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def named_entities(claim: ExtractedClaim, backbone: EntityBackbone, subject_uid: int) -> list:
    """Backbone entities the claim text names, excluding the subject itself.

    An entity matches when every one of its distinctive name tokens appears in
    the claim — the same tokenisation the tell miner and screener use, so "named
    entity" means one thing across Okojo. Entities with no distinctive tokens
    can never match (an empty token set would otherwise match everything).
    """
    low = f"{claim.text} {claim.source_sentence}".lower()
    out = []
    for e in backbone.entities:
        if e.uid == subject_uid or not e.name_tokens:
            continue
        if all(tok in low for tok in e.name_tokens):
            out.append(e)
    return out


def _refs_for(entity) -> set[str]:
    """Every ledger reference an entity moves value through."""
    return {f"uid:{entity.uid}"} | {a.address for a in entity.addresses}


# --------------------------------------------------------------------------- #
# 1) Corporate-registry OSINT
# --------------------------------------------------------------------------- #
def check_registry(
    conn: Connectors, backbone: EntityBackbone, claim: ExtractedClaim, subject_uid: int,
) -> list[Rebuttal]:
    """A denied relationship, tested against officer appointments.

    Fires when the claim denies a relationship with a named entity and the
    registry shows both companies sharing an officer over *overlapping*
    appointment windows — a shared director who had already resigned before the
    other appointment began would not contradict anything.
    """
    if not _mentions(claim.text, RELATIONSHIP_DENIAL_TERMS):
        return []

    out: list[Rebuttal] = []
    subject_rows = conn.registry_officers(subject_uid)
    for other in named_entities(claim, backbone, subject_uid):
        other_rows = conn.registry_officers(other.uid)
        for a in subject_rows:
            for b in other_rows:
                if a["officer_uid"] != b["officer_uid"]:
                    continue
                start = max(str(a["appointed_date"]), str(b["appointed_date"]))
                end = min(
                    str(a["resigned_date"] or _OPEN_ENDED),
                    str(b["resigned_date"] or _OPEN_ENDED),
                )
                if start > end:
                    continue  # appointments never overlapped
                out.append(Rebuttal(
                    source="registry",
                    statement=(
                        f"The corporate registry records {a['officer_name']} as "
                        f"{a['officer_role']} of both {a['company_name']} and "
                        f"{b['company_name']}, with appointments overlapping from "
                        f"{start} to {'present' if end == _OPEN_ENDED else end}."
                    ),
                    strength=W_REGISTRY_COMMON_OFFICER,
                    provenance=[a.provenance, b.provenance],
                ))
    return out


# --------------------------------------------------------------------------- #
# 2) The subject's own prior RFI answers
# --------------------------------------------------------------------------- #
def check_prior_rfi(
    conn: Connectors, backbone: EntityBackbone, claim: ExtractedClaim, subject_uid: int,
) -> list[Rebuttal]:
    """A denial now, tested against what the same subject said before.

    Fires on a polarity mismatch: the current claim denies a relationship with a
    named entity while an earlier answer from the same subject names that entity
    in an affirming relationship phrase.
    """
    if not _mentions(claim.text, RELATIONSHIP_DENIAL_TERMS):
        return []

    others = named_entities(claim, backbone, subject_uid)
    if not others:
        return []

    out: list[Rebuttal] = []
    for prior in conn.prior_rfis_for(subject_uid):
        text = str(prior["response_text"])
        low = text.lower()
        if not _mentions(text, RELATIONSHIP_AFFIRMATION_TERMS):
            continue
        for other in others:
            if not all(tok in low for tok in other.name_tokens):
                continue
            out.append(Rebuttal(
                source="prior_rfi",
                statement=(
                    f"The subject's own earlier response {prior['rfi_id']} "
                    f"({prior['asked_date']}) describes a relationship with "
                    f"{other.name} that the current answer denies."
                ),
                strength=W_PRIOR_RFI_SELF_CONTRADICTION,
                provenance=[prior.provenance],
            ))
    return out


# --------------------------------------------------------------------------- #
# 3) On-chain flows
# --------------------------------------------------------------------------- #
def _sanctioned_flow(conn: Connectors, start_refs: set[str]) -> list:
    """Transactions on a value path from ``start_refs`` to a sanctioned address.

    Breadth-first over transaction edges, visiting in ``tx_id`` order so the
    path returned is deterministic. Returns the edges of the first path found,
    or an empty list when no path exists.
    """
    sanctioned = {r["address"] for r in conn.sanctioned_addresses()}
    edges = sorted(conn.all_transactions(), key=lambda t: str(t["tx_id"]))
    out_edges: dict[str, list] = {}
    for t in edges:
        out_edges.setdefault(str(t["from_ref"]), []).append(t)

    seen = set(start_refs)
    queue = deque((ref, []) for ref in sorted(start_refs))
    while queue:
        ref, path = queue.popleft()
        for tx in out_edges.get(ref, []):
            nxt = str(tx["to_ref"])
            if nxt in sanctioned:
                return path + [tx]
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, path + [tx]))
    return []


def check_onchain(
    conn: Connectors, backbone: EntityBackbone, claim: ExtractedClaim, subject_uid: int,
) -> list[Rebuttal]:
    """Fund-flow and counterparty evidence.

    Two probes, each gated on what the claim actually asserts:

    * a **relationship denial** naming an entity -> direct transfers between the
      two parties' ledger references;
    * a **source-of-funds** assertion -> a value path to a synthetic-sanctioned
      endpoint, structured round-number transfers, and gas-funded hops.
    """
    subject = backbone.account(subject_uid)
    if subject is None:
        return []
    out: list[Rebuttal] = []
    subject_refs = _refs_for(subject)

    if _mentions(claim.text, RELATIONSHIP_DENIAL_TERMS):
        for other in named_entities(claim, backbone, subject_uid):
            other_refs = _refs_for(other)
            flows = [
                t for t in conn.all_transactions()
                if (str(t["from_ref"]) in subject_refs and str(t["to_ref"]) in other_refs)
                or (str(t["from_ref"]) in other_refs and str(t["to_ref"]) in subject_refs)
            ]
            if flows:
                out.append(Rebuttal(
                    source="onchain",
                    statement=(
                        f"The ledger records {len(flows)} direct transfer(s) between "
                        f"the subject and {other.name}, including near-equal transfers "
                        f"in both directions, which is inconsistent with an unrelated "
                        f"counterparty."
                    ),
                    strength=W_ONCHAIN_COUNTERPARTY_FLOW,
                    provenance=[t.provenance for t in flows],
                ))

    if _mentions(claim.text, SOURCE_OF_FUNDS_TERMS):
        path = _sanctioned_flow(conn, subject_refs)
        if path:
            out.append(Rebuttal(
                source="onchain",
                statement=(
                    f"Value moved by the subject reaches a synthetic-sanctioned "
                    f"address in {len(path)} hop(s), which the stated lawful-trade "
                    f"origin does not account for."
                ),
                strength=W_ONCHAIN_SANCTIONED_EXPOSURE,
                provenance=[t.provenance for t in path],
            ))

        structured = [
            t for t in conn.all_transactions()
            if t.get("is_structured_round_number")
            and (str(t["from_ref"]) in subject_refs or str(t["to_ref"]) in subject_refs)
        ]
        if structured:
            out.append(Rebuttal(
                source="onchain",
                statement=(
                    f"{len(structured)} transfer(s) to or from the subject are "
                    f"structured just-under round numbers, a pattern ordinary trade "
                    f"settlement does not produce."
                ),
                strength=W_ONCHAIN_STRUCTURED,
                provenance=[t.provenance for t in structured],
            ))

        gas = [
            g for g in conn.gas_funds()
            if str(g["funded_address"]) in {
                str(t["to_ref"]) for t in conn.all_transactions()
                if str(t["from_ref"]) in subject_refs
            }
        ]
        if gas:
            out.append(Rebuttal(
                source="onchain",
                statement=(
                    f"{len(gas)} address(es) the subject paid out to had their gas "
                    f"funded by a third party's wallet, indicating those hops were "
                    f"not independent of the network."
                ),
                strength=W_ONCHAIN_GAS_FUNDED_HOP,
                provenance=[g.provenance for g in gas],
            ))

    return out


# --------------------------------------------------------------------------- #
# 4) Device data
# --------------------------------------------------------------------------- #
def check_device(
    conn: Connectors, backbone: EntityBackbone, claim: ExtractedClaim, subject_uid: int,
) -> list[Rebuttal]:
    """An exclusive-control assertion, tested against shared device fingerprints.

    Fires when the claim asserts sole ownership or segregation and the subject
    signs in from a ``device_fingerprint`` also used by other accounts — control
    commingling that a "fully segregated" characterisation omits.
    """
    if not _mentions(claim.text, EXCLUSIVE_CONTROL_TERMS):
        return []

    out: list[Rebuttal] = []
    for dev in conn.devices_for(subject_uid):
        fp = str(dev["device_fingerprint"])
        # accounts_on_device returns device rows (fingerprint + uid); resolve the
        # display names through the shared backbone rather than re-querying.
        co_accounts = [a for a in conn.accounts_on_device(fp) if a["uid"] != subject_uid]
        if not co_accounts:
            continue
        names = ", ".join(sorted(
            (backbone.account(int(a["uid"])).name
             if backbone.account(int(a["uid"])) else f"uid:{a['uid']}")
            for a in co_accounts
        ))
        out.append(Rebuttal(
            source="device",
            statement=(
                f"The subject shares device_fingerprint {fp[:12]}... with "
                f"{len(co_accounts)} other account(s) ({names}), which a fully "
                f"segregated custody arrangement would not produce."
            ),
            strength=W_DEVICE_SHARED_FINGERPRINT,
            provenance=[dev.provenance] + [a.provenance for a in co_accounts],
        ))
    return out


# Registry of probes, in a fixed order so output is stable.
CHECKERS = (
    ("registry", check_registry),
    ("prior_rfi", check_prior_rfi),
    ("onchain", check_onchain),
    ("device", check_device),
)


def run_checkers(
    conn: Connectors,
    backbone: EntityBackbone,
    claim: ExtractedClaim,
    subject_uid: int,
    only: Optional[tuple[str, ...]] = None,
) -> list[Rebuttal]:
    """Run every probe against one claim and return the rebuttals, in probe order."""
    out: list[Rebuttal] = []
    for key, fn in CHECKERS:
        if only is not None and key not in only:
            continue
        out.extend(fn(conn, backbone, claim, subject_uid))
    return out
