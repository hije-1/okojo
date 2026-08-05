"""Grounded SAR Drafter (Phase 1 — template-first, no Critic).

Assembles the case artefacts (profile + anomalies, network expansion, remark
tells, advisory match) into a schema-validated :class:`SarDraft`. Every claim is
built *from* an evidence record and carries that record's provenance, so the
draft is grounded by construction; :func:`assert_grounded` then fails closed if
anything slipped through uncitable.

This runs with **no LLM** — a template is grounded by definition. Once an LLM
provider is chosen, an optional narrative-polish pass can be layered on top
*without* relaxing the grounding contract (it may only rephrase grounded claims).
The Critic loop and FinCEN rubric scoring arrive in Phase 4.
"""

from __future__ import annotations

import re
from typing import Optional

from ..advisory import AdvisoryMatch
from ..aggregator import ProfileTimeline
from ..config import jurisdiction_label
from ..connectors import Connectors
from ..network import NetworkExpansion
from ..provenance import Provenance
from ..remarks import RemarkTell
from ..rfi import ContradictionTable
from .schema import SarClaim, SarDraft, assert_calibrated, assert_grounded
from .validate import assert_resolvable


def _name_uid(conn: Connectors, uid: int) -> str:
    """'uid N (Entity Name)' — a reviewer should never see a bare account number."""
    acct = conn.get_account(int(uid))
    return f"uid {uid} ({acct['entity_name']})" if acct is not None else f"uid {uid}"


def _short_addr(addr: str) -> str:
    return (addr[:8] + "…" + addr[-4:]) if len(addr) > 14 else addr


def _plain_note(note: str) -> str:
    """Strip the miner's parenthetical jargon tags (e.g. '(attribution tell)',
    '(fee-skim tell)') so the curated rationale reads plainly in the SAR."""
    return re.sub(r"\s*\([^)]*tell\)", "", note).strip()


def _tx_author_uid(conn: Connectors, tx) -> Optional[int]:
    """The account of record on the SENDING side of a transaction: a ``uid:``
    sender directly, or an on-chain sending address resolved to its controller
    of record in the address book. ``None`` if unresolvable."""
    fr = str(tx["from_ref"])
    if fr.startswith("uid:"):
        return int(fr[4:])
    rec = conn.get_address(fr)
    if rec is not None and rec["controller_uid"] is not None:
        return int(rec["controller_uid"])
    return None


def _accounts_named_by(conn: Connectors, matched_terms) -> list[int]:
    """Accounts whose entity name contains a matched name-token — i.e. the
    account(s) a control-alias remark names. Evidence-derived (the accounts
    table), never the answer key."""
    uids: set[int] = set()
    for a in conn.all_accounts():
        nm = str(a["entity_name"]).lower()
        if any(str(t).lower() in nm for t in matched_terms):
            uids.add(int(a["uid"]))
    return sorted(uids)

_DISCLAIMER = (
    "DRAFT — generated from synthetic data for research. A human investigator must "
    "review, decide, and file. This is not a filed SAR and carries no regulatory effect."
)

# Drafting policy: which mined tells may enter a SAR. The miner is a
# DATASET-WIDE screen by design; the SAR is a SUBJECT-SCOPED artifact. A tell
# enters the draft only when its transaction touches the subject or the case's
# expanded network — a resolvable pointer to an unrelated party's transaction
# is real evidence, but not this subject's (Phase 7 grounding-completeness;
# carried in critic_config()["drafting"] and published in
# docs/sar-critic-methodology.md).
TELL_SCOPE = "subject_network_closure"


def _tells_in_closure(
    conn: Connectors, expansion: NetworkExpansion, tells: list[RemarkTell],
) -> list[RemarkTell]:
    """Filter the dataset-wide tell screen down to the subject's evidence
    closure: the subject itself plus every account and address the expansion
    actually reached in this run. Order-preserving; empty for an isolated
    subject — the honest result, which the Critic then surfaces as an
    uncovered element for human review rather than papering over."""
    acct_refs = {
        f"uid:{str(n).split(':', 1)[1]}"
        for n in expansion.graph.nodes if str(n).startswith("acct:")
    }
    addrs = {
        str(n).split(":", 1)[1]
        for n in expansion.graph.nodes if str(n).startswith("addr:")
    }
    tx_refs = {t["tx_id"]: (t["from_ref"], t["to_ref"]) for t in conn.all_transactions()}
    # Address-book tells have no transaction; their closure membership is the
    # saved address, plus every address the saving customer controls. This
    # reproduces exactly the closure refs the pre-redesign chain transaction
    # carried (its {controller_wallet, saved_address} endpoints), so the tell
    # surfaces in the same subjects' SARs as before the model change.
    abk: dict[str, tuple[str, ...]] = {}
    for e in conn.address_book():
        controlled = tuple(str(a["address"]) for a in conn.addresses_for(int(e["uid"])))
        abk[str(e["entry_id"])] = (str(e["address"]),) + controlled
    kept: list[RemarkTell] = []
    for hit in tells:
        if hit.source_kind == "address_book":
            refs = abk.get(hit.tx_id, ())
        else:
            refs = tx_refs.get(hit.tx_id, ())
        if any(r in acct_refs or r in addrs for r in refs):
            kept.append(hit)
    return kept


def _owners_of(conn: Connectors, prov: list[Provenance]) -> set[int]:
    """Account uids owning the cited evidence rows (best-effort, read-only).

    Reference material (sdn_list) and the subject's own narrative surfaces
    (rfi/rfi_prior) resolve to no third-party owner here — they are either
    not account evidence or definitionally the subject's."""
    owners: set[int] = set()
    addr_owner: dict[str, Optional[int]] = {}

    def _addr(ref: str) -> Optional[int]:
        if ref not in addr_owner:
            rec = conn.get_address(ref)
            addr_owner[ref] = (
                int(rec["controller_uid"])
                if rec is not None and rec["controller_uid"] is not None else None
            )
        return addr_owner[ref]

    def _ref(ref: str) -> None:
        if str(ref).startswith("uid:"):
            owners.add(int(str(ref)[4:]))
        else:
            u = _addr(str(ref))
            if u is not None:
                owners.add(u)

    tx_refs = None
    for p in prov:
        if p.source == "accounts" and p.row_key.startswith("uid:"):
            owners.add(int(p.row_key.split(":")[1]))
        elif p.source == "transactions":
            if tx_refs is None:
                tx_refs = {t["tx_id"]: (t["from_ref"], t["to_ref"])
                           for t in conn.all_transactions()}
            for ref in tx_refs.get(p.row_key, ()):
                _ref(ref)
        elif p.source == "gas_funding":
            for part in p.row_key.split("->"):
                _ref(part)
        elif p.source == "addresses":
            _ref(p.row_key)
        elif p.source == "devices":
            owners.add(int(p.row_key.rsplit(":", 1)[1]))
        elif p.source == "kyc_docs":
            owners.update(int(a["uid"]) for a in conn.accounts_with_kyc(p.row_key))
        elif p.source == "registry":
            for rec in conn.all_registry():
                if rec["registry_id"] == p.row_key:
                    owners.update({int(rec["company_uid"]), int(rec["officer_uid"])})
    return owners


def _attribution_note(
    conn: Connectors, expansion: NetworkExpansion, subject_uid: int,
    prov: list[Provenance],
) -> str:
    """One appended sentence naming every non-subject account whose records a
    claim cites — linked network accounts and (separately labelled) any
    dataset-level context outside the subject's own network. Empty when the
    cited rows are all the subject's own. The reader of a subject-scoped
    claim must be able to tell whose evidence it rests on from the text."""
    others = _owners_of(conn, prov) - {subject_uid}
    if not others:
        return ""
    net_uids = {
        int(str(n).split(":")[1])
        for n in expansion.graph.nodes if str(n).startswith("acct:")
    }

    def _named(uids: list[int]) -> str:
        parts = []
        for u in uids:
            acct = conn.get_account(u)
            parts.append(f"uid {u} ({acct['entity_name']})" if acct else f"uid {u}")
        return ", ".join(parts)

    linked = sorted(u for u in others if u in net_uids)
    outside = sorted(u for u in others if u not in net_uids)
    bits = []
    if linked:
        bits.append(f"records of linked account(s) in the subject's network — {_named(linked)}")
    if outside:
        bits.append(
            f"dataset-wide screening context from {_named(outside)}, "
            f"account(s) outside the subject's own network"
        )
    return " This also draws on " + " and ".join(bits) + "."


def build_sar(
    conn: Connectors,
    profile: ProfileTimeline,
    expansion: NetworkExpansion,
    tells: list[RemarkTell],
    advisory: Optional[AdvisoryMatch],
    max_tells: int = 4,
    contradictions: Optional[ContradictionTable] = None,
) -> SarDraft:
    subject = conn.get_account(profile.subject_uid)
    claims: list[SarClaim] = []

    # WHO — subject identity (grounded in the account row).
    claims.append(SarClaim(
        element="who",
        statement=(
            f"The subject is account uid {profile.subject_uid} ({profile.subject_name}), "
            f"a {profile.entity_type} with declared residence "
            f"{jurisdiction_label(profile.residence_country)} and account status "
            f"'{profile.account_status}'."
        ),
        provenance=[subject.provenance],
    ))

    # WHAT — each surfaced anomaly becomes a grounded claim. The severity leads in
    # plain words ("High severity — ...") rather than a bracketed tag.
    for anomaly in profile.anomalies:
        claims.append(SarClaim(
            element="what",
            statement=f"{anomaly.severity.capitalize()} severity — {anomaly.statement}",
            provenance=list(anomaly.provenance),
        ))

    # NETWORK — expansion reach and synthetic-sanctioned exposure.
    sanctioned_prov: list[Provenance] = []
    for addr in expansion.sanctioned_addresses_reached:
        rec = conn.get_address(addr)
        if rec is not None:
            sanctioned_prov.append(rec.provenance)
    if sanctioned_prov:
        claims.append(SarClaim(
            element="network",
            statement=(
                f"From the subject, network expansion reaches "
                f"{len(expansion.reached_account_uids)} linked account(s) within "
                f"{expansion.max_hops} hop(s) and touches "
                f"{len(expansion.sanctioned_addresses_reached)} sanctioned address(es) "
                f"(synthetic) — potential downstream exposure for analyst review."
            ),
            provenance=[subject.provenance] + sanctioned_prov,
        ))

    # TELL — attribution tells from free-text remarks, gated to the subject's
    # evidence closure (see TELL_SCOPE): the screen is dataset-wide, the SAR
    # is not. When the transaction belongs to a linked network account rather
    # than the subject, the claim SAYS so — citing a network member's evidence
    # is legitimate investigative practice, but the reader must be able to
    # tell whose evidence it is from the claim text alone.
    abk_owner = {
        str(e["entry_id"]): (int(e["uid"]), str(e["address"]))
        for e in conn.address_book()
    }
    tx_by_id = {t["tx_id"]: t for t in conn.all_transactions()}

    def _name_first(uid: int) -> str:
        acct = conn.get_account(uid)
        return f"{acct['entity_name']} (uid {uid})" if acct is not None else f"uid {uid}"

    # Parties are NAMED in prose (derivable from the cited evidence row / the
    # accounts reference table), never cited as extra rows — so a tell claim
    # cites only its own source row and never reaches outside the subject's
    # evidence closure (the P1b subject-closure property). Same discipline as
    # _attribution_note.
    for hit in _tells_in_closure(conn, expansion, tells)[:max_tells]:
        if hit.source_kind == "address_book":
            owner_uid, saved_addr = abk_owner.get(hit.tx_id, (None, ""))
            if owner_uid == profile.subject_uid:
                lead = (f'The subject saved wallet {_short_addr(saved_addr)} in its own '
                        f'address book under the label "{hit.remark}"')
            else:
                lead = (f"A linked account in the subject's network — "
                        f"{_name_uid(conn, owner_uid)}, not the subject itself — saved wallet "
                        f'{_short_addr(saved_addr)} in its address book under the label '
                        f'"{hit.remark}"')
            statement = f"{lead} — {_plain_note(hit.note)}. Flagged for analyst review."
        else:
            tx = tx_by_id.get(hit.tx_id)
            author = _tx_author_uid(conn, tx) if tx is not None else None
            if author == profile.subject_uid:
                who_lead = "The subject"
            elif author is not None:
                who_lead = (f"A linked account in the subject's network — "
                            f"{_name_uid(conn, author)}, not the subject itself —")
            else:
                who_lead = "A linked account in the subject's network"
            if hit.category == "control_alias":
                named = _accounts_named_by(conn, hit.matched_terms)
                to_ref = str(tx["to_ref"]) if tx is not None else ""
                named_full = ", ".join(_name_first(u) for u in named) or "a known case account"
                named_plain = ", ".join(str(conn.get_account(u)["entity_name"])
                                        for u in named) or "that account"
                statement = (
                    f'{who_lead} paid wallet {_short_addr(to_ref)} and, in its own transfer, '
                    f'labelled that wallet "{hit.remark}", naming {named_full} as the '
                    f"wallet's owner. This ties the receiving wallet to {named_plain} rather "
                    f"than to the independent third party it is presented as. Flagged for "
                    f"analyst review."
                )
            else:
                statement = (
                    f'{who_lead} labelled one of its own transfers "{hit.remark}" — '
                    f"{_plain_note(hit.note)}. Flagged for analyst review."
                )
        claims.append(SarClaim(
            element="tell", statement=statement, provenance=[hit.provenance],
        ))

    # ADVISORY — regulatory grounding + the SAR key term to cite. The match's
    # corroboration is case- and dataset-level by versioned retrieval policy,
    # so its provenance may include records of accounts outside the subject's
    # own network (e.g. a watchlist name-hit elsewhere in the data). Those are
    # carried — hiding the match's real basis would weaken defensibility —
    # and ATTRIBUTED in the claim text so the reader can tell they are
    # corroboration context, not the subject's own records.
    if advisory is not None:
        corroboration_note = _attribution_note(
            conn, expansion, profile.subject_uid, list(advisory.provenance),
        )
        claims.append(SarClaim(
            element="advisory",
            statement=(
                f"The subject's case text matches FinCEN Advisory {advisory.advisory_id} "
                f"on the terms {', '.join(advisory.matched_terms)}. FinCEN instructs filers to "
                f"reference key term {advisory.sar_key_term}.{corroboration_note}"
            ),
            provenance=list(advisory.provenance),
        ))

    # RFI — the subject's narrative, surfaced alongside the evidence.
    rfis = conn.rfi_for(profile.subject_uid)
    if rfis:
        rfi = rfis[0]
        claims.append(SarClaim(
            element="rfi",
            statement=(
                f"In RFI {rfi['rfi_id']}, the subject states its funds derive from lawful trade "
                "settlement. This assertion is surfaced alongside the evidence above for "
                "analyst review."
            ),
            provenance=[rfi.provenance],
        ))

    # CONTRADICTION — each adjudicated contradiction, citing BOTH sides: the RFI
    # row carrying the assertion and every evidence row rebutting it. Calibrated
    # deliberately: the draft says the evidence is *inconsistent with* the
    # assertion and surfaces it for review; it never concludes the subject lied.
    if contradictions is not None:
        for adj in contradictions.contradictions:
            rebuttal_prov = [p for r in adj.rebuttals for p in r.provenance]
            all_prov = _dedup([adj.provenance] + rebuttal_prov)
            claims.append(SarClaim(
                element="contradiction",
                statement=(
                    f"RFI {contradictions.rfi_id} claim {adj.claim_id} asserts: "
                    f'"{adj.claim_text}" {len(adj.rebuttals)} finding(s) across '
                    f"{len(adj.sources)} independent source type(s) are inconsistent with "
                    f"that assertion (combined confidence {adj.confidence:.2f}): "
                    + " ".join(f"({i}) {r.statement}"
                               for i, r in enumerate(adj.rebuttals, 1))
                    + " Surfaced for analyst review."
                    # drafter-owned attribution: whose records the rebuttals cite
                    + _attribution_note(conn, expansion, profile.subject_uid, all_prov)
                ),
                provenance=all_prov,
            ))

    filing_note = "Human review required before any filing decision."
    if advisory is not None:
        filing_note = (
            f"If filed after human review, reference key term {advisory.sar_key_term} in SAR "
            f"field 2 ('Filing Institution Note to FinCEN') and the narrative. "
            f"Associated SAR fields: {advisory.sar_fields}."
        )

    draft = SarDraft(
        subject_uid=profile.subject_uid,
        subject_name=profile.subject_name,
        advisory_id=advisory.advisory_id if advisory else None,
        sar_key_term=advisory.sar_key_term if advisory else None,
        filing_note=filing_note,
        disclaimer=_DISCLAIMER,
        claims=claims,
    )

    # SAR-validation contract, fail closed: (1) no claim without a provenance
    # pointer; (2) no pointer to a row that does not exist; (3) no over-claiming
    # (uncalibrated) language — a miscalibrated draft is rejected and surfaced,
    # never silently passed.
    assert_grounded(draft)
    assert_resolvable(conn, draft)
    assert_calibrated(draft)
    return draft


# --------------------------------------------------------------------------- #
# Gap-targeted claim builders (the Critic's revision inputs).
#
# Each fills one FinCEN-rubric element the template-first draft omits, *only*
# from evidence already retrieved for this case. Every builder returns a grounded
# claim or ``None`` — ``None`` means the element is genuinely unsupported by the
# evidence, so the Critic loop flags it for human review rather than inventing it.
# --------------------------------------------------------------------------- #

def _dedup(prov: list[Provenance]) -> list[Provenance]:
    """Order-preserving de-duplication (Provenance is frozen/hashable)."""
    return list(dict.fromkeys(prov))


def _when_claim(profile: ProfileTimeline) -> Optional[SarClaim]:
    """WHEN — the timeframe spanned by the surfaced timeline (first..last event)."""
    if not profile.events:
        return None
    first, last = profile.events[0], profile.events[-1]
    return SarClaim(
        element="when",
        statement=(
            f"The activity surfaced for review spans {first.timestamp} to "
            f"{last.timestamp}, from the earliest account/login event through the "
            f"most recent surfaced transaction."
        ),
        provenance=_dedup(list(first.provenance) + list(last.provenance)),
    )


def _where_claim(conn: Connectors, profile: ProfileTimeline) -> Optional[SarClaim]:
    """WHERE — declared residence vs. the geographies observed in login sessions."""
    subject = conn.get_account(profile.subject_uid)
    if subject is None:
        return None
    ip_events = [e for e in profile.events if e.kind == "ip_login"]
    prov = _dedup([subject.provenance] + [p for e in ip_events for p in e.provenance])
    geo_note = (
        f" Logins were observed across {len(ip_events)} session(s) (see cited IP "
        f"logs), surfaced against the declared residence for analyst review."
        if ip_events else ""
    )
    return SarClaim(
        element="where",
        statement=(
            f"The subject declares residence in "
            f"{jurisdiction_label(profile.residence_country)}.{geo_note}"
        ),
        provenance=prov,
    )


def _predicate_claim(
    conn: Connectors, expansion: NetworkExpansion, advisory: Optional[AdvisoryMatch],
) -> Optional[SarClaim]:
    """WHY — the potential predicate, grounded in sanctioned exposure and/or advisory."""
    prov: list[Provenance] = []
    bases: list[str] = []
    for addr in expansion.sanctioned_addresses_reached:
        rec = conn.get_address(addr)
        if rec is not None:
            prov.append(rec.provenance)
    if prov:
        bases.append("synthetic-sanctioned on-chain exposure")
    if advisory is not None:
        prov.extend(advisory.provenance)
        bases.append(f"the typology in FinCEN Advisory {advisory.advisory_id}")
    if not prov:
        return None  # no grounded predicate basis -> flag for human review
    return SarClaim(
        element="predicate",
        statement=(
            f"The evidence surfaces a potential predicate of sanctions-evasion / "
            f"illicit-finance activity, grounded in {' and '.join(bases)}. This is "
            f"proposed for analyst assessment, not a determination."
        ),
        provenance=_dedup(prov),
    )


def _how_claim(
    conn: Connectors, profile: ProfileTimeline, expansion: NetworkExpansion,
) -> Optional[SarClaim]:
    """HOW — the concrete mechanism(s) evidenced (structured / gas-funding /
    reused-KYC), each stated plainly and naming any party involved."""
    prov: list[Provenance] = []
    parts: list[str] = []

    struct = [t for t in conn.transactions_for_uid(profile.subject_uid)
              if t.get("is_structured_round_number")]
    if struct:
        parts.append(
            f"{len(struct)} transfer(s) to or from the subject are structured just under "
            f"round numbers, a pattern ordinary trade settlement does not produce."
        )
        prov.extend(t.provenance for t in struct)

    if expansion.gas_funding_links:
        gas_prov = {
            (g["funder_address"], g["funded_address"]): g.provenance
            for g in conn.gas_funds()
        }
        links = [
            link for link in expansion.gas_funding_links
            if (link["funder_address"], link["funded_address"]) in gas_prov
        ]
        if links:
            prov.extend(gas_prov[(link["funder_address"], link["funded_address"])]
                        for link in links)
            # Name the controller in prose (derived from the address table); the
            # claim cites the gas-funding rows only, staying inside closure.
            funder_uids = sorted({
                int(rec["controller_uid"])
                for link in links
                if (rec := conn.get_address(str(link["funder_address"]))) is not None
                and rec["controller_uid"] is not None
            })
            named = ", ".join(_name_uid(conn, u) for u in funder_uids) or "a third-party wallet"
            parts.append(
                f"The 'non-custodial' hop wallet(s) the subject paid had their transaction "
                f"fees (gas) paid by a wallet controlled by {named}, tying those supposedly "
                f"independent hops back to that account."
            )

    subject = conn.get_account(profile.subject_uid)
    kyc_id = subject.get("kyc_doc_id") if subject is not None else None
    if kyc_id:
        shared = conn.accounts_with_kyc(kyc_id)
        if len(shared) > 1:
            others = ", ".join(_name_uid(conn, int(a["uid"])) for a in shared
                               if int(a["uid"]) != profile.subject_uid)
            parts.append(
                f"The subject's KYC document is reused to open separate account(s) "
                f"({others}) — the same paperwork behind supposedly distinct entities."
            )
            prov.extend(a.provenance for a in shared)

    if not prov:
        return None
    return SarClaim(
        element="how",
        statement="How the activity operates: " + " ".join(parts) + " Surfaced for analyst review.",
        provenance=_dedup(prov),
    )


# Rubric-key -> builder. The loop consults this to fill a gap; a missing key or a
# builder returning None means the gap is left for human review, never fabricated.
def gap_fill_claims(
    conn: Connectors,
    profile: ProfileTimeline,
    expansion: NetworkExpansion,
    advisory: Optional[AdvisoryMatch],
    gap_keys: list[str],
) -> list[SarClaim]:
    """Build grounded claims for whichever requested rubric gaps the evidence supports."""
    builders = {
        "when": lambda: _when_claim(profile),
        "where": lambda: _where_claim(conn, profile),
        "why": lambda: _predicate_claim(conn, expansion, advisory),
        "how": lambda: _how_claim(conn, profile, expansion),
    }
    out: list[SarClaim] = []
    for key in gap_keys:
        build = builders.get(key)
        if build is None:
            continue
        claim = build()
        if claim is not None:
            out.append(claim)
    return out
