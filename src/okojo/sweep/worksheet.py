"""Remediation worksheet — triaged, grounded, fail-closed.

One row per account the sweep surfaced (exposed or adjacent-review-only), each
carrying: the exposure evidence, BOTH hold-system statuses, any reconciliation
gap, the internal-tag flag, a recommended action from the published calibrated
vocabulary, and provenance for every fact its statement asserts. The worksheet
mirrors the SAR drafter's discipline: a row with no citation, or a citation
that does not resolve to a real evidence row, fails the build — the worksheet
is never emitted partially grounded.

Action assignment is a fixed rule over the row's own fields (published in
``docs/sweep-methodology.md``); triage order is the published
``(action_severity, -exposure_usdt, hops, uid)``. The worksheet *proposes* and
*flags* — a human reviews, decides, and actions any change.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance
from ..sar import GroundingReport, GroundingResolver, UnresolvableCitationError
from . import ACTION_VOCABULARY, REQUIRED_ARTIFACTS, calibrated_language_violations
from .designation import Designation
from .exposure import ExposureResult
from .verify import StatusGap


def _is_present(value) -> bool:
    """A KYC-artifact ``present`` cell as a bool, robust to the CSV round-trip.

    pandas reads a clean True/False column as bool, but an empty or object-typed
    cell can arrive as ``None``/``"False"``/numpy bool — and ``bool("False")`` is
    ``True``. Comparing the string form avoids that trap (the S2 NaN lesson)."""
    return str(value) == "True"

# Sort sentinel for adjacency rows, which have no hop distance: they sort
# after any real hop count within their (already less severe) action band.
_NO_HOPS_SENTINEL = 10**6


class CalibratedLanguageError(ValueError):
    """A signal-type output asserted a legal effect of a foreign listing."""


class WorksheetRow(BaseModel):
    """One account's remediation line — the sweep's per-account deliverable."""

    uid: int
    entity_name: str
    exposure_usdt: float           # 0.0 for adjacency (non-flow) rows
    hops: Optional[int]            # None for adjacency rows
    direct: bool
    warehouse_status: str
    admin_status: str
    gap_type: Optional[str]
    internal_tag_flag: bool
    # Part I-B S3 flags. ``exposure_timing`` classifies WHEN an exposed row's
    # driving flow occurred vs the designation date (None for review-only rows);
    # ``kyc_missing_artifacts`` are the required-but-absent onboarding artifacts;
    # ``staff_account`` marks membership of the staff register (drives the
    # insider-linkage action when it coincides with a device overlap).
    exposure_timing: Optional[str] = None   # pre_designation | post_designation | timeless_control
    kyc_missing_artifacts: list[str] = []
    staff_account: bool = False
    recommended_action: str        # one of ACTION_VOCABULARY
    statement: str
    provenance: list[Provenance]

    def is_grounded(self) -> bool:
        return len(self.provenance) > 0


def _action_for(row_kind: str, is_signal: bool, gap_type: Optional[str],
                warehouse_status: str, admin_status: str,
                internal_tag_flag: bool, is_staff: bool = False,
                link_types: Optional[list[str]] = None) -> str:
    """The fixed assignment rule — one action per row, from the row's fields.

    Exposed accounts under a SIGNAL-type (foreign national-list) designation
    take the review-tier ``flags_foreign_signal_exposure_for_review`` — a
    foreign listing is a timestamped risk signal, never an obligation, so no
    hold is proposed or confirmed. Exposed accounts under an OBLIGATION-type
    (domestic) designation keep the original rule: a reconciliation gap outranks
    everything (the hold state must be trued up first), a consistent existing
    block is confirmed, otherwise a designation hold review is proposed. A
    name-only listing match is a review-tier identity row.

    Adjacency rows, most severe first: a **staff account** (per the staff
    register) whose non-flow linkage is a **device overlap** into the exposed
    network is the named severe insider flag — an employee-owned account sharing
    a device with the designated ring is a conflict-of-interest finding well
    above generic linkage. Otherwise the internal tag carries its own named flag
    (flagged, never obeyed); otherwise the generic non-flow-linkage review flag.
    Staff membership is read from the register alone, never a role label.
    """
    if row_kind == "exposed":
        if is_signal:
            return "flags_foreign_signal_exposure_for_review"
        if gap_type is not None:
            return "flags_reconciliation_gap"
        if warehouse_status == "blocked" and admin_status == "blocked":
            return "proposes_confirm_existing_hold"
        return "proposes_designation_hold_review"
    if row_kind == "name_match":
        return "flags_name_match_for_identity_review"
    if is_staff and "shared_device" in (link_types or []):
        return "flags_insider_staff_device_overlap"
    if internal_tag_flag:
        return "flags_internal_tag_for_review"
    return "flags_for_review_non_flow_linkage"


_TIMING_PHRASE = {
    "timeless_control": (
        "Exposure timing: control of a designated wallet is a timeless fact, "
        "not bound to any transaction date."
    ),
    "pre_designation": (
        "Exposure timing: the driving transactions predate the designation date "
        "— pre-existing exposure the designation surfaces."
    ),
    "post_designation": (
        "Exposure timing: driving activity postdates the designation date "
        "— post-designation exposure, the categorically worse fact."
    ),
}


def _statement(row_kind: str, entity_name: str, designation: Designation,
               hops: Optional[int], direct: bool, exposure_usdt: float,
               warehouse_status: str, admin_status: str,
               gap_type: Optional[str], internal_tag_flag: bool,
               link_types: Optional[list[str]] = None,
               exposure_timing: Optional[str] = None,
               kyc_missing: Optional[list[str]] = None,
               is_staff_device_overlap: bool = False) -> str:
    """Calibrated row narrative — asserts only facts the row's pointers back.

    Signal-type output uses risk-signal language and never asserts a legal
    effect of a foreign listing (enforced by the calibrated-language check).
    """
    did = designation.designation_id
    is_signal = designation.obligation_vs_signal == "signal"
    if row_kind == "exposed":
        kind = "direct" if direct else "indirect"
        if is_signal:
            parts = [
                f"{entity_name}: {kind} flow exposure to {designation.source_regime} "
                f"national-list entry {did} (a timestamped risk signal listed since "
                f"{designation.listed_since}, not a designation obligation) at hop "
                f"distance {hops}; tainted amount {exposure_usdt:,.2f} USDT from the "
                "cited transactions; surfaced for review."
            ]
        else:
            parts = [
                f"{entity_name}: {kind} flow exposure to designation "
                f"{did} at hop distance {hops}; "
                f"tainted amount {exposure_usdt:,.2f} USDT from the cited transactions."
            ]
        if exposure_timing in _TIMING_PHRASE:
            parts.append(_TIMING_PHRASE[exposure_timing])
        if kyc_missing:
            parts.append(
                "KYC completeness: missing required onboarding artifact(s) on file "
                f"— {', '.join(kyc_missing)} (measured against the published "
                "required-artifact standard)."
            )
    elif row_kind == "name_match":
        parts = [
            f"{entity_name}: customer name matches an individual on "
            f"{designation.source_regime}'s national list ({did}, listed since "
            f"{designation.listed_since}); no domestic designation exists and no "
            "flow exposure was found; surfaced for identity review."
        ]
    elif is_staff_device_overlap:
        links = " and ".join((link_types or [])).replace("_", " ")
        parts = [
            f"{entity_name}: no flow exposure to designation {did}; the account is "
            "on the staff-account register (conflict-of-interest monitoring) and "
            f"its non-flow linkage ({links}) is a staff device overlap with the "
            "exposed network — surfaced for review as a potential insider link."
        ]
    else:
        links = " and ".join((link_types or [])).replace("_", " ")
        parts = [
            f"{entity_name}: no flow exposure to designation {did}; "
            f"surfaced for review on non-flow linkage ({links}) to exposed accounts."
        ]
    parts.append(
        f"Hold status: warehouse={warehouse_status}, admin={admin_status}"
        + (f" — reconciliation gap ({gap_type})." if gap_type else " (consistent).")
    )
    if internal_tag_flag:
        parts.append(
            "The account carries an internal do-not-block style tag; the tag "
            "is flagged for review as a finding and exempts nothing."
        )
    return " ".join(parts)


def build_worksheet(
    conn: Connectors,
    designation: Designation,
    exposure: ExposureResult,
    gaps: list[StatusGap],
    name_matches: Optional[list] = None,
) -> list[WorksheetRow]:
    """Build, triage, and fail-closed-validate the remediation worksheet.

    ``name_matches`` (the designated-name screen output) contributes review-tier
    identity rows for any matched account NOT already surfaced by flow exposure
    or non-flow adjacency — the additive foreign-list identity coverage. A match
    that is already exposed (e.g. the domestic live name matching an exposed
    shell) adds no row, so a domestic worksheet is byte-unchanged.
    """
    is_signal = designation.obligation_vs_signal == "signal"
    wh = {int(r["uid"]): r for r in conn.warehouse_holds()}
    adm = {int(r["uid"]): r for r in conn.admin_holds()}
    accounts = {int(r["uid"]): r for r in conn.all_accounts()}
    gap_by_uid = {g.uid: g for g in gaps}
    # Part I-B S3 evidence planes: transaction dates (timing), KYC artifacts on
    # file (completeness), and the staff register (insider linkage).
    tx_date = {str(t["tx_id"]): str(t["timestamp"])[:10] for t in conn.all_transactions()}
    kyc_recs = {(int(r["uid"]), str(r["artifact_type"])): r for r in conn.kyc_artifacts()}
    staff_recs = {int(r["uid"]): r for r in conn.staff_register()}
    designation_date = designation.designation_date

    rows: list[WorksheetRow] = []

    def _exposure_timing(hops: Optional[int], base_provenance: list[Provenance]) -> Optional[str]:
        """When did this exposure's driving flow occur vs the designation date?

        Control (hops == 0) is timeless — no transaction dates it (the same
        discipline that excludes hops-0 from the in-window key). Flow exposure is
        post-designation iff any cited driving transaction postdates the
        designation; otherwise it is pre-existing exposure the designation
        surfaces. Read from the row's OWN cited transaction dates — an
        independent read of the same evidence the generator's key derives."""
        if hops is None:
            return None
        if hops == 0:
            return "timeless_control"
        dates = [tx_date[p.row_key] for p in base_provenance
                 if p.source == "transactions" and p.row_key in tx_date]
        return "post_designation" if any(d > designation_date for d in dates) else "pre_designation"

    def _kyc_gap(uid: int, entity_type: str) -> tuple[list[str], list[Provenance]]:
        """Required-but-absent onboarding artifacts for an in-scope account,
        measured against the published standard, each absence cited to its
        artifact row. A required artifact with no row at all is a gap too."""
        missing: list[str] = []
        prov: list[Provenance] = []
        for art in REQUIRED_ARTIFACTS.get(entity_type, []):
            rec = kyc_recs.get((uid, art))
            if rec is None or not _is_present(rec["present"]):
                missing.append(art)
                if rec is not None:
                    prov.append(rec.provenance)
        return sorted(missing), prov

    def _add(uid: int, entity_name: str, *, row_kind: str,
             hops: Optional[int], direct: bool, exposure_usdt: float,
             base_provenance: list[Provenance],
             link_types: Optional[list[str]] = None) -> None:
        # Ring accounts always carry a hold row in both systems (unchanged). A
        # Part-IV counterparty-review-subject can be flow-exposed yet carry no
        # hold row (review subjects are outside the hold tables' coverage set):
        # an absent row reads as "no_hold" and cites nothing, so the row still
        # grounds on its exposure provenance. Byte-identical for every legacy
        # account, which always resolves both rows.
        w, a = wh.get(uid), adm.get(uid)
        wh_status = str(w["hold_status"]) if w is not None else "no_hold"
        adm_status = str(a["hold_status"]) if a is not None else "no_hold"
        gap = gap_by_uid.get(uid)
        acct = accounts[uid]
        tag_flag = acct.get("internal_tag") is not None
        is_staff = uid in staff_recs
        prov = list(base_provenance)
        if w is not None:
            prov.append(w.provenance)
        if a is not None:
            prov.append(a.provenance)
        if tag_flag:
            prov.append(Provenance(
                source=acct.provenance.source, row_key=acct.provenance.row_key,
                field="internal_tag", detail="internal tag flagged for review, never obeyed",
            ))

        # S3 timing (exposed rows) + KYC completeness (in-scope exposed rows).
        timing = _exposure_timing(hops, base_provenance) if row_kind == "exposed" else None
        kyc_missing: list[str] = []
        if row_kind == "exposed":
            kyc_missing, kyc_prov = _kyc_gap(uid, str(acct["entity_type"]))
            prov += kyc_prov

        # S3 insider linkage: a staff account whose non-flow linkage is a device
        # overlap into the exposed network. The register row is cited.
        action = _action_for(
            row_kind, is_signal, gap.gap_type if gap else None,
            wh_status, adm_status, tag_flag,
            is_staff=is_staff, link_types=link_types,
        )
        insider = action == "flags_insider_staff_device_overlap"
        if insider:
            prov.append(staff_recs[uid].provenance)

        rows.append(WorksheetRow(
            uid=uid,
            entity_name=entity_name,
            exposure_usdt=exposure_usdt,
            hops=hops,
            direct=direct,
            warehouse_status=wh_status,
            admin_status=adm_status,
            gap_type=gap.gap_type if gap else None,
            internal_tag_flag=tag_flag,
            exposure_timing=timing,
            kyc_missing_artifacts=kyc_missing,
            staff_account=is_staff,
            recommended_action=action,
            statement=_statement(
                row_kind, entity_name, designation, hops, direct, exposure_usdt,
                wh_status, adm_status,
                gap.gap_type if gap else None, tag_flag, link_types,
                exposure_timing=timing, kyc_missing=kyc_missing,
                is_staff_device_overlap=insider,
            ),
            provenance=prov,
        ))

    for e in exposure.exposed:
        _add(e.uid, e.entity_name, row_kind="exposed", hops=e.hops, direct=e.direct,
             exposure_usdt=e.tainted_amount_usdt, base_provenance=e.provenance)
    for a in exposure.adjacent:
        _add(a.uid, a.entity_name, row_kind="adjacent", hops=None, direct=False,
             exposure_usdt=0.0, base_provenance=a.provenance,
             link_types=a.link_types)
    # Name-only identity rows: a matched account surfaced by NEITHER flow nor
    # linkage (the additive foreign-list coverage — e.g. an individual on a
    # foreign national list with no wallet and no domestic designation).
    already = {r.uid for r in rows}
    for m in (name_matches or []):
        if m.uid in already:
            continue
        _add(m.uid, m.entity_name, row_kind="name_match", hops=None, direct=False,
             exposure_usdt=0.0, base_provenance=list(m.provenance))

    rows.sort(key=lambda r: (
        ACTION_VOCABULARY.index(r.recommended_action),
        -r.exposure_usdt,
        r.hops if r.hops is not None else _NO_HOPS_SENTINEL,
        r.uid,
    ))

    if is_signal:
        assert_calibrated_signal_language(rows)
    assert_worksheet_resolvable(conn, rows)
    return rows


def assert_calibrated_signal_language(rows: list[WorksheetRow]) -> None:
    """Fail closed: no signal-type worksheet statement may ASSERT a legal effect
    of a foreign listing. Authored clean, this never trips in practice — it is a
    defence-in-depth tripwire so a future wording change cannot silently let
    obligation language into signal output."""
    for r in rows:
        hits = calibrated_language_violations(r.statement)
        if hits:
            raise CalibratedLanguageError(
                f"signal-type worksheet row uid:{r.uid} asserts a legal effect "
                f"({', '.join(hits)}); calibrated language required"
            )


def worksheet_grounding_report(conn: Connectors, rows: list[WorksheetRow]) -> GroundingReport:
    """Grounding + resolvability coverage over worksheet rows.

    Reuses the SAR :class:`GroundingReport` container (same semantics: a row is
    *resolved* iff it is grounded and every one of its pointers names a real
    evidence row) so the two pipelines report the same numbers the same way.
    """
    resolver = GroundingResolver(conn)
    grounded = 0
    resolved = 0
    unresolved: list = []
    for r in rows:
        if r.is_grounded():
            grounded += 1
        bad = [p for p in r.provenance if not resolver.resolves(p)]
        if r.is_grounded() and not bad:
            resolved += 1
        if bad:
            unresolved.append((r, bad))
    return GroundingReport(
        total_claims=len(rows), grounded_claims=grounded,
        resolved_claims=resolved, unresolved=unresolved,
    )


def assert_worksheet_resolvable(conn: Connectors, rows: list[WorksheetRow]) -> None:
    """Fail closed: every row cites at least one pointer and every pointer
    resolves to a real evidence row — or the worksheet is not emitted."""
    report = worksheet_grounding_report(conn, rows)
    if not report.fully_grounded:
        raise UnresolvableCitationError(
            f"{report.total_claims - report.grounded_claims} worksheet row(s) carry no provenance"
        )
    if report.unresolved:
        cites = "; ".join(
            f"uid:{r.uid}:{p.cite()}" for r, ps in report.unresolved for p in ps
        )
        raise UnresolvableCitationError(
            f"{len(report.unresolved)} worksheet row(s) cite unresolvable evidence: {cites}"
        )
