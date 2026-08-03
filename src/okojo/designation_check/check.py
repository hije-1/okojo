"""Subject-as-seed designation check (v1.1) — the case-side mirror of the sweep.

The sweep answers "a designation arrived — who is exposed?"; this answers the
reverse an investigator actually asks in case mode: "I have a subject — do they
or their cluster touch ANY designation?" It is a **read-only composition** of
machinery the sweep/geo/identity layers already own — nothing here re-derives a
score, a variant rule, or a lifecycle state; it seeds those engines with the
subject and reads back what they say. It writes to no chain and introduces no
new versioned policy (the badge state-machine + coverage statement are
derivation logic, covered by tests, not tunable constants).

Scope of a check (design lock 2026-08-03):
  * Party-type designations (``sdn_style`` / ``national_ct`` /
    ``counterparty_service`` — every non-territory listing in the table):
    name + transliteration-variant screen, address membership, flow exposure
    (hops / tainted / direct) with the pre/post-designation timing split, the
    counterparty lifecycle *state* where the subject is exposed to a
    counterparty-service listing, and corroboration against published
    identifiers where the designation carries them.
  * Territory designations: the geo dossier assembled *for the subject* per
    designated territory (the one-signal rule surfaces it or a clean line).

The **badge** reflects the SUBJECT'S OWN posture only (their account's
name/variant/address hits + corroboration); cluster hits live in the network
notice, never the badge — the badge answers one question, "is this subject a
match?". A ``name_only_dismissed`` collision is GREEN with a standing dismissal
line (an adjudicated collision is not an open item), never amber.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..agency.decisions import decide_corroboration
from ..connectors import Connectors
from ..geo.signals import assemble_dossier
from ..identity.variants import screen_name_variants
from ..sweep import LIST_SOURCE_REGISTRY
from ..sweep.designation import Designation, designation_from_record, match_designated_name
from ..sweep.exposure import sweep_exposure
from ..sweep.geo import territory_profile
from ..sweep.lifecycle import (
    counterparty_dealings,
    derive_counterparty_lifecycle_state,
    has_post_designation_dealing,
    is_stop_verified,
)

# --- badge states (subject's own posture) ------------------------------------
BADGE_NO_MATCH = "no_match"                 # green
BADGE_POSSIBLE = "possible_match"           # amber
BADGE_CORROBORATED = "match_corroborated"   # red

# The three corroboration verdicts, re-exported for the caller's convenience
# (owned by agency.decide_corroboration — not redefined here).
CORROBORATED = "corroborated_true_hit"
POSSIBLE = "possible_match_needs_human"
DISMISSED = "name_only_dismissed"


def _attr(rec, field: str) -> str:
    """One identity cell as a clean string (empty / NaN -> "") — mirrors the
    sweep's ``_identity_attr`` robustness so an absent identifier reads as
    unknown, never a spurious ``"nan"``. Local (2 lines) to keep the case path
    from importing the whole sweep pipeline."""
    val = rec.get(field) if rec is not None else None
    s = "" if val is None else str(val).strip()
    return "" if s.lower() == "nan" else s


def _standing_phrase(obligation_vs_signal: str, listed_since: str) -> str:
    """The cross-list doctrine in investigator-facing language: an obligation
    list binds; a signal list is early warning, carrying its listed-since date."""
    if obligation_vs_signal == "obligation":
        return "a blocking-obligation list"
    return f"an early-warning signal list, listed since {listed_since}"


class DesignationMeta(BaseModel):
    """Every displayed hit carries its designation's metadata, plain-languaged."""

    designation_id: str
    designated_name: str
    program: str
    list_type: str
    source_regime: str
    obligation_vs_signal: str
    listed_since: str
    standing_phrase: str


def _meta(d: Designation) -> DesignationMeta:
    return DesignationMeta(
        designation_id=d.designation_id,
        designated_name=d.designated_name,
        program=d.program,
        list_type=d.list_type,
        source_regime=d.source_regime,
        obligation_vs_signal=d.obligation_vs_signal,
        listed_since=d.listed_since,
        standing_phrase=_standing_phrase(d.obligation_vs_signal, d.listed_since),
    )


class PartyHit(BaseModel):
    """A subject-own name/variant/address match to a party-type designation."""

    meta: DesignationMeta
    match_kind: str                       # "name" | "variant" | "address"
    score: Optional[float] = None         # None for an address membership
    matched_form: Optional[str] = None    # matched variant / matched address
    rule_path: list[str] = []             # variant equivalence-class ids (else [])
    corroboration_outcome: Optional[str] = None
    corroboration_rationale: Optional[str] = None
    mismatched_fields: list[str] = []
    provenance: list[str]


class DismissalLine(BaseModel):
    """A name collision screened AND adjudicated away (identifiers mismatch).

    Rendered as a standing, always-visible line under the badge — the honest
    face of visible-absence: the clean conclusion AND the work that produced it.
    """

    meta: DesignationMeta
    match_kind: str
    score: Optional[float] = None
    mismatched_fields: list[str]
    provenance: list[str]


class FlowExposureLine(BaseModel):
    meta: DesignationMeta
    uid: int
    hops: int
    direct: bool
    tainted_amount_usdt: float
    timing: str                           # pre_designation | post_designation | timeless_control
    provenance: list[str]


class CounterpartyStateLine(BaseModel):
    """Display-only lifecycle *state* where the subject is exposed to a
    counterparty-service designation — no proposal, no disposition."""

    meta: DesignationMeta
    uid: int
    state: str
    acknowledged: bool
    stop_verified: bool
    provenance: list[str]


class TerritoryLine(BaseModel):
    meta: DesignationMeta
    territory_label: str
    surfaced: bool
    signal_ids: list[str]
    note: str
    provenance: list[str]


class NetworkNotice(BaseModel):
    """A designation match/exposure in the subject's NETWORK (not the subject).

    Names the names; notice only — the Network tab stays the deep view."""

    meta: DesignationMeta
    uid: int
    entity_name: str
    kind: str                             # "name" | "variant" | "flow"
    hops: Optional[int] = None            # for flow notices
    provenance: list[str]


class CoverageStatement(BaseModel):
    designations_screened: int
    list_sources_screened: int
    declared_not_ingested: list[str]      # human-readable list names


class DesignationCheckResult(BaseModel):
    subject_uid: int
    subject_name: str
    badge_state: str
    subject_hits: list[PartyHit]
    dismissals: list[DismissalLine]
    flow_exposures: list[FlowExposureLine]
    counterparty_states: list[CounterpartyStateLine]
    territory_lines: list[TerritoryLine]
    network_notices: list[NetworkNotice]
    coverage: CoverageStatement


def compute_badge(subject_hits: list[PartyHit]) -> str:
    """The subject's headline posture from their OWN active hits.

    ``subject_hits`` are the subject's non-dismissed name/variant/address
    matches (dismissed collisions are carried separately and never escalate the
    badge). RED iff any active hit is a corroborated true hit; AMBER for any
    other active hit (a name/variant match with no disqualifying identifier, or
    an address membership); GREEN when there is no active hit.
    """
    if any(h.corroboration_outcome == CORROBORATED for h in subject_hits):
        return BADGE_CORROBORATED
    if subject_hits:
        return BADGE_POSSIBLE
    return BADGE_NO_MATCH


def _exposure_timing(hops: int, provenance_objs, tx_date: dict[str, str],
                     designation_date: str) -> str:
    """Pre/post-designation split — an independent read of the SAME evidence the
    sweep's ``worksheet._exposure_timing`` reads (control is timeless; flow is
    post-designation iff any cited driving transaction postdates the listing).
    A parity test pins this to the sweep's per-uid answer key so the two engines
    can never silently diverge."""
    if hops == 0:
        return "timeless_control"
    dates = [tx_date[p.row_key] for p in provenance_objs
             if p.source == "transactions" and p.row_key in tx_date]
    return "post_designation" if any(d > designation_date for d in dates) else "pre_designation"


def run_designation_check(conn: Connectors, subject_uid: int,
                          cluster_uids, *,
                          reference_date: Optional[str] = None) -> DesignationCheckResult:
    """Screen the subject (+ their network cluster) against every designation.

    ``cluster_uids`` is the case's Network-Expander uid set at the selected hops
    (the check sees exactly what the investigator sees on the Network tab). Pure
    and read-only: no chain is written, no store is mutated.
    """
    subject_uid = int(subject_uid)
    cluster = {int(u) for u in cluster_uids} | {subject_uid}

    accounts = {int(a["uid"]): a for a in conn.all_accounts()}
    subject_name = str(accounts.get(subject_uid, {}).get("entity_name", f"uid {subject_uid}")) \
        if subject_uid in accounts else f"uid {subject_uid}"
    tx_date = {str(t["tx_id"]): str(t["timestamp"])[:10] for t in conn.all_transactions()}

    # Controlled-address book per uid (for address membership).
    controlled: dict[int, set[str]] = {}
    for rec in conn.all_addresses():
        if rec["controller_uid"] is not None:
            controlled.setdefault(int(rec["controller_uid"]), set()).add(str(rec["address"]))

    designations = [designation_from_record(r) for r in conn.all_designations()]
    party = [d for d in designations if d.list_type != "territory"]
    territory = [d for d in designations if d.list_type == "territory"]

    subject_hits: list[PartyHit] = []
    dismissals: list[DismissalLine] = []
    flow_exposures: list[FlowExposureLine] = []
    counterparty_states: list[CounterpartyStateLine] = []
    network_notices: list[NetworkNotice] = []
    source_regimes: set[str] = set()

    for d in party:
        meta = _meta(d)
        source_regimes.add(d.source_regime)

        # -- name + variant screen (cluster-scoped), with corroboration -------- #
        name_hits = [m for m in match_designated_name(conn, d) if m.uid in cluster]
        name_uids = {m.uid for m in name_hits}
        variant_hits = [m for m in screen_name_variants(conn, d.designated_name,
                                                         exclude_uids=name_uids)
                        if m.uid in cluster]

        id_rec = conn.designation_identifier_for(d.designation_id)
        identifiers = ({f: _attr(id_rec, f) for f in ("dob", "nationality", "doc_type", "doc_number")}
                       if id_rec is not None else None)

        def _corroborate(uid: int):
            """(outcome, rationale, mismatched, prov) or None when not corroborable."""
            if identifiers is None:
                return None
            kyc_rec = conn.kyc_identity_attributes_for(uid)
            if kyc_rec is None:
                return None
            kyc = {f: _attr(kyc_rec, f) for f in ("dob", "nationality", "doc_type", "doc_number")}
            rec = decide_corroboration(uid, d.designated_name, kyc, identifiers,
                                       provenance=[kyc_rec.provenance.cite(), id_rec.provenance.cite()])
            return (rec.outcome, rec.rationale,
                    list(rec.evidence.get("mismatched_fields", [])), list(rec.provenance))

        for kind, hits in (("name", name_hits), ("variant", variant_hits)):
            for m in hits:
                prov = [p.cite() for p in m.provenance]
                matched_form = getattr(m, "matched_variant", None)
                rule_path = list(getattr(m, "rule_path", []))
                if m.uid == subject_uid:
                    corr = _corroborate(m.uid)
                    outcome = corr[0] if corr else None
                    if outcome == DISMISSED:
                        dismissals.append(DismissalLine(
                            meta=meta, match_kind=kind, score=m.score,
                            mismatched_fields=corr[2], provenance=prov + corr[3]))
                    else:
                        subject_hits.append(PartyHit(
                            meta=meta, match_kind=kind, score=m.score,
                            matched_form=matched_form, rule_path=rule_path,
                            corroboration_outcome=outcome,
                            corroboration_rationale=(corr[1] if corr else None),
                            mismatched_fields=(corr[2] if corr else []),
                            provenance=prov + (corr[3] if corr else [])))
                else:
                    network_notices.append(NetworkNotice(
                        meta=meta, uid=m.uid, entity_name=m.entity_name,
                        kind=kind, provenance=prov))

        # -- address membership (subject own -> hit; cluster -> notice) -------- #
        designated_addr = set(d.designated_addresses)
        for uid in sorted(cluster):
            hit_addrs = sorted(controlled.get(uid, set()) & designated_addr)
            if not hit_addrs:
                continue
            prov = [f"addresses[{a}]" for a in hit_addrs]
            if uid == subject_uid:
                subject_hits.append(PartyHit(
                    meta=meta, match_kind="address", matched_form="; ".join(hit_addrs),
                    provenance=prov))
            else:
                network_notices.append(NetworkNotice(
                    meta=meta, uid=uid,
                    entity_name=str(accounts.get(uid, {}).get("entity_name", f"uid {uid}")),
                    kind="address", provenance=prov))

        # -- flow exposure (subject own -> line; cluster -> notice) ------------ #
        if d.designated_addresses:
            exp = sweep_exposure(conn, d.designated_addresses)
            for e in exp.exposed:
                if e.uid not in cluster:
                    continue
                if e.uid == subject_uid:
                    flow_exposures.append(FlowExposureLine(
                        meta=meta, uid=e.uid, hops=e.hops, direct=e.direct,
                        tainted_amount_usdt=e.tainted_amount_usdt,
                        timing=_exposure_timing(e.hops, e.provenance, tx_date, d.designation_date),
                        provenance=[p.cite() for p in e.provenance]))
                else:
                    network_notices.append(NetworkNotice(
                        meta=meta, uid=e.uid, entity_name=e.entity_name, kind="flow",
                        hops=e.hops, provenance=[p.cite() for p in e.provenance]))

            # -- counterparty lifecycle STATE (display-only) ------------------ #
            if d.list_type == "counterparty_service" and subject_uid in exp.exposed_uids():
                dealings = counterparty_dealings(conn, d, subject_uid)
                acks = conn.acknowledgments_for(subject_uid)
                ack_dates = sorted(str(a["acknowledged_date"]) for a in acks
                                   if str(a["counterparty_designation_id"]) == d.designation_id)
                acknowledged = bool(ack_dates)
                stop_verified = (acknowledged
                                 and is_stop_verified(dealings, ack_dates[-1]))
                state = derive_counterparty_lifecycle_state(
                    notification_drafted=has_post_designation_dealing(dealings, d.designation_date),
                    acknowledged=acknowledged, stop_verified=stop_verified,
                    outcome="hold_pending")  # display-only: no disposition proposed
                counterparty_states.append(CounterpartyStateLine(
                    meta=meta, uid=subject_uid, state=state,
                    acknowledged=acknowledged, stop_verified=stop_verified,
                    provenance=[t.provenance.cite() for t in dealings]))

    # -- territory branch (subject-seeded geo dossier per territory) ----------- #
    territory_lines: list[TerritoryLine] = []
    subj_acct = accounts.get(subject_uid)
    for d in territory:
        source_regimes.add(d.source_regime)
        prof = territory_profile(conn, d)
        if prof is None or subj_acct is None:
            continue
        ref = reference_date or d.designation_date
        carriers = {str(r["carrier"]) for r in conn.exclusive_carriers_for(prof.territory_code)}
        kyc = conn.get_kyc(str(subj_acct["kyc_doc_id"]))
        dossier = assemble_dossier(
            subject_uid, str(subj_acct["entity_name"]),
            territory=prof, reference_date=ref,
            ip_records=conn.ip_logs_for(subject_uid),
            phone_records=conn.phone_registrations_for(subject_uid),
            kyc_doc_records=[kyc] if kyc is not None else [],
            account_record=subj_acct,
            timezone_records=conn.device_timezones_for(subject_uid),
            validity_records=conn.kyc_artifact_validity_for(subject_uid),
            exclusive_carriers=carriers,
        )
        note = (f"Location signals toward {prof.territory_label}"
                if dossier.surfaced
                else f"No location signals toward {prof.territory_label}")
        territory_lines.append(TerritoryLine(
            meta=_meta(d), territory_label=prof.territory_label,
            surfaced=dossier.surfaced, signal_ids=dossier.signal_ids(),
            note=note, provenance=[p.cite() for p in dossier.provenance]))

    # -- coverage statement (visible absence) ---------------------------------- #
    declared_not_ingested = [reg["name"] for reg in LIST_SOURCE_REGISTRY.values()
                             if not reg["ingested"]]
    coverage = CoverageStatement(
        designations_screened=len(designations),
        list_sources_screened=len(source_regimes),
        declared_not_ingested=declared_not_ingested,
    )

    return DesignationCheckResult(
        subject_uid=subject_uid,
        subject_name=subject_name,
        badge_state=compute_badge(subject_hits),
        subject_hits=subject_hits,
        dismissals=dismissals,
        flow_exposures=flow_exposures,
        counterparty_states=counterparty_states,
        territory_lines=territory_lines,
        network_notices=network_notices,
        coverage=coverage,
    )
