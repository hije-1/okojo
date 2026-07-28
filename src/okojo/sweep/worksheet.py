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
from . import ACTION_VOCABULARY, calibrated_language_violations
from .designation import Designation
from .exposure import ExposureResult
from .verify import StatusGap

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
    recommended_action: str        # one of ACTION_VOCABULARY
    statement: str
    provenance: list[Provenance]

    def is_grounded(self) -> bool:
        return len(self.provenance) > 0


def _action_for(row_kind: str, is_signal: bool, gap_type: Optional[str],
                warehouse_status: str, admin_status: str,
                internal_tag_flag: bool) -> str:
    """The fixed assignment rule — one action per row, from the row's fields.

    Exposed accounts under a SIGNAL-type (foreign national-list) designation
    take the review-tier ``flags_foreign_signal_exposure_for_review`` — a
    foreign listing is a timestamped risk signal, never an obligation, so no
    hold is proposed or confirmed. Exposed accounts under an OBLIGATION-type
    (domestic) designation keep the original rule: a reconciliation gap outranks
    everything (the hold state must be trued up first), a consistent existing
    block is confirmed, otherwise a designation hold review is proposed. A
    name-only listing match is a review-tier identity row. Adjacency rows: the
    internal tag carries its own named flag (flagged, never obeyed); otherwise
    the generic non-flow-linkage review flag.
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
    if internal_tag_flag:
        return "flags_internal_tag_for_review"
    return "flags_for_review_non_flow_linkage"


def _statement(row_kind: str, entity_name: str, designation: Designation,
               hops: Optional[int], direct: bool, exposure_usdt: float,
               warehouse_status: str, admin_status: str,
               gap_type: Optional[str], internal_tag_flag: bool,
               link_types: Optional[list[str]] = None) -> str:
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
    elif row_kind == "name_match":
        parts = [
            f"{entity_name}: customer name matches an individual on "
            f"{designation.source_regime}'s national list ({did}, listed since "
            f"{designation.listed_since}); no domestic designation exists and no "
            "flow exposure was found; surfaced for identity review."
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

    rows: list[WorksheetRow] = []

    def _add(uid: int, entity_name: str, *, row_kind: str,
             hops: Optional[int], direct: bool, exposure_usdt: float,
             base_provenance: list[Provenance],
             link_types: Optional[list[str]] = None) -> None:
        w, a = wh[uid], adm[uid]
        gap = gap_by_uid.get(uid)
        acct = accounts[uid]
        tag_flag = acct.get("internal_tag") is not None
        prov = list(base_provenance) + [w.provenance, a.provenance]
        if tag_flag:
            prov.append(Provenance(
                source=acct.provenance.source, row_key=acct.provenance.row_key,
                field="internal_tag", detail="internal tag flagged for review, never obeyed",
            ))
        rows.append(WorksheetRow(
            uid=uid,
            entity_name=entity_name,
            exposure_usdt=exposure_usdt,
            hops=hops,
            direct=direct,
            warehouse_status=str(w["hold_status"]),
            admin_status=str(a["hold_status"]),
            gap_type=gap.gap_type if gap else None,
            internal_tag_flag=tag_flag,
            recommended_action=_action_for(
                row_kind, is_signal, gap.gap_type if gap else None,
                str(w["hold_status"]), str(a["hold_status"]), tag_flag,
            ),
            statement=_statement(
                row_kind, entity_name, designation, hops, direct, exposure_usdt,
                str(w["hold_status"]), str(a["hold_status"]),
                gap.gap_type if gap else None, tag_flag, link_types,
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
