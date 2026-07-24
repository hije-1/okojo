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

from typing import Optional

from ..advisory import AdvisoryMatch
from ..aggregator import ProfileTimeline
from ..connectors import Connectors
from ..network import NetworkExpansion
from ..provenance import Provenance
from ..remarks import RemarkTell
from ..rfi import ContradictionTable
from .schema import SarClaim, SarDraft, assert_grounded
from .validate import assert_resolvable

_DISCLAIMER = (
    "DRAFT — generated from synthetic data for research. A human investigator must "
    "review, decide, and file. This is not a filed SAR and carries no regulatory effect."
)


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
            f"a {profile.entity_type} with declared residence {profile.residence_country} "
            f"and account status '{profile.account_status}'."
        ),
        provenance=[subject.provenance],
    ))

    # WHAT — each surfaced anomaly becomes a grounded claim.
    for anomaly in profile.anomalies:
        claims.append(SarClaim(
            element="what",
            statement=f"The profile flags [{anomaly.severity}] {anomaly.statement}",
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
                f"Network expansion from the subject surfaces "
                f"{len(expansion.reached_account_uids)} linked account(s) within "
                f"{expansion.max_hops} hop(s) and reaches "
                f"{len(expansion.sanctioned_addresses_reached)} synthetic-sanctioned "
                f"address(es), indicating potential downstream exposure for analyst review."
            ),
            provenance=[subject.provenance] + sanctioned_prov,
        ))

    # TELL — attribution tells from free-text remarks.
    for hit in tells[:max_tells]:
        claims.append(SarClaim(
            element="tell",
            statement=(
                f'A remark on {hit.tx_id} surfaces a possible attribution tell '
                f'("{hit.remark}"): {hit.note}.'
            ),
            provenance=[hit.provenance],
        ))

    # ADVISORY — regulatory grounding + the SAR key term to cite.
    if advisory is not None:
        claims.append(SarClaim(
            element="advisory",
            statement=(
                f"The subject's case text matches FinCEN Advisory {advisory.advisory_id} "
                f"on term(s): {', '.join(advisory.matched_terms)}. FinCEN instructs filers to "
                f"reference key term {advisory.sar_key_term}."
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
                f"The subject's RFI response ({rfi['rfi_id']}) states funds derive from lawful "
                "trade settlement; this assertion is surfaced alongside the above evidence for "
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
            claims.append(SarClaim(
                element="contradiction",
                statement=(
                    f"RFI {contradictions.rfi_id} claim {adj.claim_id} asserts: "
                    f'"{adj.claim_text}" The retrieved evidence is inconsistent with that '
                    f"assertion on {len(adj.sources)} independent source(s) "
                    f"({', '.join(adj.sources)}; evidence weight {adj.confidence:.2f}): "
                    + " ".join(r.statement for r in adj.rebuttals)
                    + " This contradiction is surfaced for analyst review."
                ),
                provenance=_dedup([adj.provenance] + rebuttal_prov),
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

    # Grounding contract, fail closed in two steps: (1) no claim without a
    # provenance pointer; (2) no pointer to a row that does not exist.
    assert_grounded(draft)
    assert_resolvable(conn, draft)
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
        statement=f"The subject declares residence in {profile.residence_country}.{geo_note}",
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
    """HOW — the concrete mechanism(s) evidenced (structured / gas-funding / reused-KYC)."""
    prov: list[Provenance] = []
    mechs: list[str] = []

    struct = [t for t in conn.transactions_for_uid(profile.subject_uid)
              if t.get("is_structured_round_number")]
    if struct:
        mechs.append("structured round-number transfers")
        prov.extend(t.provenance for t in struct)

    if expansion.gas_funding_links:
        gas_prov = {
            (g["funder_address"], g["funded_address"]): g.provenance
            for g in conn.gas_funds()
        }
        gas_ps = [
            gas_prov[(link["funder_address"], link["funded_address"])]
            for link in expansion.gas_funding_links
            if (link["funder_address"], link["funded_address"]) in gas_prov
        ]
        if gas_ps:
            mechs.append("gas-funding linkage unmasking non-custodial hops")
            prov.extend(gas_ps)

    subject = conn.get_account(profile.subject_uid)
    kyc_id = subject.get("kyc_doc_id") if subject is not None else None
    if kyc_id:
        shared = conn.accounts_with_kyc(kyc_id)
        if len(shared) > 1:
            mechs.append("reused KYC documentation across accounts")
            prov.extend(a.provenance for a in shared)

    if not prov:
        return None
    return SarClaim(
        element="how",
        statement=(
            f"The activity exhibits {', '.join(mechs)} (mechanism surfaced for "
            f"analyst review)."
        ),
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
