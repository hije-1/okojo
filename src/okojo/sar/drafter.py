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
from .schema import SarClaim, SarDraft, assert_grounded

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

    # RFI — surfaced (not adjudicated in Phase 1; contradiction-checking is Phase 5).
    rfis = conn.rfi_for(profile.subject_uid)
    if rfis:
        rfi = rfis[0]
        claims.append(SarClaim(
            element="rfi",
            statement=(
                f"The subject's RFI response ({rfi['rfi_id']}) states funds derive from lawful "
                "trade settlement; this assertion is surfaced alongside the above evidence for "
                "analyst review (claim-by-claim contradiction testing is out of scope this phase)."
            ),
            provenance=[rfi.provenance],
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

    # Grounding contract: fail closed on any uncitable claim.
    assert_grounded(draft)
    return draft
