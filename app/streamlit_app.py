"""Okojo — Streamlit demo.

Pick a synthetic subject and watch one case flow end-to-end: an anomaly-flagged
timeline, the network graph with gas-funding collapse, per-account on-chain
sanctioned-exposure scoring, remark tells, SDN/alias watchlist screening, the
matched FinCEN advisory, a claim-by-claim RFI contradiction table, a grounded
SAR draft, and the tamper-evident audit trail.

Run it:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from okojo.advisory import RETRIEVAL_VERSION, retrieval_config
from okojo.casegraph import CaseGraphStore
from okojo.connectors import Connectors
from okojo.narrator import NARRATOR_VERSION, narrate_chain
from okojo.network import build_roster
from okojo.orchestrator import run_case
from okojo.orchestrator.pipeline import default_out_dir
from okojo.provenance import Provenance
from okojo.remarks import SCREEN_THRESHOLD
from okojo.remarks.miner import _ALIAS_THRESHOLD, _PHRASE_THRESHOLD
from okojo.sar.critic import FINCEN_RUBRIC
from okojo.scorer import SCORING_VERSION, scoring_config
from okojo.agency import AGENCY_VERSION
from okojo.geo import GEO_VERSION
from okojo.identity import IDENTITY_VERSION, OWNERSHIP_CONTROL_THRESHOLD
from okojo.sweep import (
    GAP_TAXONOMY,
    SWEEP_VERSION,
    Designation,
    DesignationParseError,
    designation_from_record,
    parse_designation,
    run_sweep,
    sweep_config,
)

# Brand logo lives at the repo root; resolve off it so the path holds regardless
# of the working directory the app is launched from.
_LOGO_PATH = str(Path(__file__).resolve().parents[1] / "okojo-logo.png")

# ONE of the three hand-maintained status surfaces (README status block,
# CLAUDE.md status block, and this on-screen caption) — update all three at
# every phase sign-off.
_PHASE = "Phase 9"

st.set_page_config(
    page_title="Okojo — Crypto-Investigations Co-Pilot",
    page_icon=_LOGO_PATH,
    layout="wide",
)
# The logo is rendered as a fixed-width image at the top of the sidebar (see
# main()) rather than via st.logo(): st.logo tops out ~32px, too small to read.

# Semantic colours (kept off brand blue — blue is chrome only). "low" uses a
# friendly green (universal "go" = lowest concern), so the brand blue never
# collides with a severity/risk meaning.
_SEVERITY_COLOR = {"high": "#dc2626", "medium": "#f59e0b", "low": "#16a34a"}
_RISK_GREY = "#6b7280"

# Human-readable labels for the machine anomaly codes surfaced as roster chips.
_ANOMALY_LABEL = {
    "sanctioned_jurisdiction_ip": "Sanctioned IP",
    "geo_ip_residence_mismatch": "Geo/IP mismatch",
    "vpn_elevation": "VPN elevation",
    "reused_kyc_document": "Reused KYC",
    "shared_device_fingerprint": "Shared device",
}

_ANOMALY_SEVERITY = {
    "sanctioned_jurisdiction_ip": "high",
    "geo_ip_residence_mismatch": "medium",
    "vpn_elevation": "medium",
    "reused_kyc_document": "high",
    "shared_device_fingerprint": "high",
}

# Timeline event kinds -> (display label, accent colour). Unknown kinds fall
# back to the raw kind string in grey, so a new connector never renders blank.
_EVENT_KIND_STYLE = {
    "account_registration": ("Account opened", "#334155"),
    "ip_login": ("Login", "#0ea5e9"),
    "transaction_deposit": ("Deposit", "#16a34a"),
    "transaction_withdrawal": ("Withdrawal", "#b45309"),
    "transaction_onchain": ("On-chain transfer", "#7c3aed"),
}

_ROLE_LABEL = {
    "ultimate_controller": "Ultimate controller",
    "family_cutout_director": "Cutout director",
    "employee_cutout": "Employee cutout",
    "licensed_trust_intermediary": "Licensed trust",
    "shell_trading": "Shell trading",
    "privileged_internal_redherring": "Internal (flagged)",
    "recidivist_mule": "Recidivist mule",
    "noise": "Ordinary",
}


@st.cache_resource
def get_connectors() -> Connectors:
    return Connectors()


def _set_subject(uid: int) -> None:
    """Callback: make ``uid`` the case subject.

    Runs as a widget callback (before the script reruns), so it can safely
    update the selectbox-bound ``subject_uid`` state without the
    "modified after instantiation" error a plain inline mutation would raise.
    """
    st.session_state.subject_uid = uid


def _chip(text: str, color: str) -> str:
    """A small rounded pill in the given accent colour (hex, e.g. ``#dc2626``)."""
    return (
        f"<span style='display:inline-block;padding:1px 8px;margin:2px 4px 2px 0;"
        f"border-radius:10px;font-size:0.72rem;font-weight:600;line-height:1.5;"
        f"color:{color};background:{color}1a;border:1px solid {color}55;'>{text}</span>"
    )


def _cites(provs) -> str:
    """Render one Provenance, or any iterable of them, as 'src[key]; src[key]'.

    THE shared provenance formatter — every claim the UI surfaces cites through
    this one function, so pointers read identically on every tab (the grounding
    contract's UI half: a claim without its pointer is a rendering bug)."""
    if provs is None:
        return ""
    if isinstance(provs, Provenance):
        provs = [provs]
    return "; ".join(p.cite() for p in provs)


def _source_caption(provs, prefix: str = "source") -> None:
    """The standard one-line citation caption under a surfaced claim."""
    text = _cites(provs)
    if text:
        st.caption(f"{prefix}: {text}")


def _diff_html(a: str, b: str) -> tuple[str, str]:
    """Return (a_html, b_html) with the characters that differ highlighted, so a
    reviewer can see *exactly* where a name and a watchlist alias diverge
    (e.g. Hill -> Holl). Amber marks are chrome, not a semantic risk colour."""
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    mark = "<span style='background:#fde68a;color:#1a2330;border-radius:2px;padding:0 1px;'>"
    a_out: list[str] = []
    b_out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        aseg, bseg = a[i1:i2], b[j1:j2]
        if tag == "equal":
            a_out.append(aseg)
            b_out.append(bseg)
        else:
            if aseg:
                a_out.append(f"{mark}{aseg}</span>")
            if bseg:
                b_out.append(f"{mark}{bseg}</span>")
    return "".join(a_out), "".join(b_out)


def _roster_card_html(row, risk=None) -> str:
    """Designed chip card for one roster account (signals + badges).

    The severity risk-rail is the card container's own left border (see
    ``_ROSTER_CSS``), keyed per row, so it stays bound to the card box. ``risk``
    (a ``RiskScore`` or ``None``) adds an on-chain sanctioned-exposure chip — a
    distinct signal from the anomaly-severity rail, so the two aren't conflated.
    """
    star = "★ " if row.is_subject else ""
    role = _ROLE_LABEL.get(row.role, row.role)

    parts: list[str] = []
    if risk is not None:
        parts.append(_chip(
            f"▲ Exposure {risk.score:.2f} · {risk.band}",
            _SEVERITY_COLOR.get(risk.band, _RISK_GREY),
        ))
    for code in row.anomaly_codes[:2]:
        parts.append(_chip(
            _ANOMALY_LABEL.get(code, code),
            _SEVERITY_COLOR.get(_ANOMALY_SEVERITY.get(code, ""), _RISK_GREY),
        ))
    extra = len(row.anomaly_codes) - 2
    if extra > 0:
        parts.append(_chip(f"+{extra} more", _RISK_GREY))
    if row.internal_flagged:
        parts.append(_chip("⚑ Do-not-block", "#b45309"))
    if not row.anomaly_codes and not row.internal_flagged:
        parts.append(_chip("No flags surfaced", _RISK_GREY))

    if row.has_case_file:
        parts.append(_chip("◉ Case file on record", "#334155"))

    return (
        f"<div style='font-size:0.95rem;'>{star}<b>{row.name}</b>"
        f"<span style='color:{_RISK_GREY};font-size:0.8rem;'> · {role} · uid {row.uid}</span></div>"
        f"<div style='margin-top:4px;'>{''.join(parts)}</div>"
        f"<div style='color:{_RISK_GREY};font-size:0.7rem;margin-top:2px;'>"
        f"source: accounts[uid:{row.uid}] · exposure decomposes in the Sanctions tab</div>"
    )


_ROSTER_CSS = """
<style>
[class*="st-key-roster_row_"] {
    border: 1px solid rgba(150, 152, 165, 0.45);
    border-radius: 0 10px 10px 0;   /* square left edge so the severity rail sits flush */
    padding: 8px 16px;
    margin-bottom: 10px;
    background: rgba(150, 152, 165, 0.04);
}
/* Severity risk-rail = the card's own left border (bound to the card box). */
[class*="st-key-roster_row_high_"]   { border-left: 4px solid #dc2626; }
[class*="st-key-roster_row_medium_"] { border-left: 4px solid #f59e0b; }
[class*="st-key-roster_row_low_"]    { border-left: 4px solid #16a34a; }
[class*="st-key-roster_row_none_"]   { border-left: 4px solid #6b7280; }
/* Cancel Streamlit's -16px markdown-container margin (assumes a trailing <p>;
   our cards end in a <div>, so it would otherwise pull the chips past the border). */
[class*="st-key-roster_row_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0; }
</style>
"""


def _render_roster(roster, risk_by_uid=None) -> None:
    risk_by_uid = risk_by_uid or {}
    st.markdown(_ROSTER_CSS, unsafe_allow_html=True)
    for row in roster:
        sev = row.worst_severity or "none"
        with st.container(key=f"roster_row_{sev}_{row.uid}"):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                st.markdown(_roster_card_html(row, risk_by_uid.get(row.uid)), unsafe_allow_html=True)
            with c2:
                if row.is_subject:
                    st.caption("● current")
                else:
                    st.button(
                        "Investigate →", key=f"inv_{row.uid}",
                        on_click=_set_subject, args=(row.uid,),
                        use_container_width=True,
                    )


# Adjudicated verdict -> (display text, accent colour). These are the LIVE output
# of the contradiction checker, not scenario labels.
_RFI_VERDICT = {
    "contradicted": ("Contradicted by evidence", "#dc2626"),
    "qualified": ("Qualified — evidence cuts against part of it", "#f59e0b"),
    "uncontested": ("Tested, nothing found against it", "#16a34a"),
    "unverifiable": ("Unverifiable — no evidence speaks to it", "#6b7280"),
}

# Evidence surface -> how it is described in the UI.
_RFI_SOURCE_LABEL = {
    "registry": "Corporate registry",
    "prior_rfi": "Subject's own prior RFI",
    "onchain": "On-chain flows",
    "device": "Device data",
}


def _render_rfi(rfi, table=None, decomposition=None) -> None:
    st.subheader("RFI contradiction table")
    st.caption(
        "Each claim in the subject's response is tested against corporate-registry, "
        "prior-RFI, on-chain and device evidence. Verdicts and confidences below are "
        "**produced live by the checker**, not scenario labels. Only *contradicted* is a "
        "flag; *qualified* and *unverifiable* are deliberately kept separate so the "
        "checker cannot inflate its own hit rate. Every verdict is proposed for human "
        "review — none is a determination."
    )
    if rfi is None:
        st.info(
            "No RFI on record for this subject. In this scenario the licensed-trust "
            "intermediary (uid 500000003) is the RFI subject."
        )
        return

    st.markdown(f"**{rfi.rfi_id}** · subject uid {rfi.uid}")
    _source_caption(rfi.provenance)
    st.markdown("**Investigator question**")
    st.markdown(f"> {rfi.question}")
    st.markdown("**Account-holder response**")
    st.markdown(f"> {rfi.response_text}")

    if table is None:
        st.warning("Contradiction checker did not run for this subject.")
        return

    s = table.summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Claims tested", s["claims"])
    c2.metric("Contradicted", s["contradicted"])
    c3.metric("Qualified", s["verdicts"]["qualified"])

    st.markdown("---")
    aligned = {c.claim_id: c for c in (decomposition.claims if decomposition else [])}
    for adj in table.adjudications:
        label, color = _RFI_VERDICT.get(adj.verdict, (adj.verdict, _RISK_GREY))
        chips = _chip(f"{adj.claim_id} · {label}", color)
        if adj.rebuttals:
            chips += "  " + _chip(f"evidence weight {adj.confidence:.2f}", "#334155")
        st.markdown(f"{chips}<br>{adj.claim_text}", unsafe_allow_html=True)
        _source_caption(adj.provenance, prefix="verdict source")

        src = aligned.get(adj.claim_id)
        if src is not None:
            st.caption(
                f"Decomposed from the response (alignment {src.alignment_score:.0f}): "
                f"“{src.source_sentence}” · source: {_cites(src.provenance)}"
            )

        if adj.rebuttals:
            with st.expander(
                f"{len(adj.rebuttals)} rebuttal(s) across "
                f"{len(adj.sources)} source(s): {', '.join(adj.sources)}"
            ):
                for r in adj.rebuttals:
                    st.markdown(
                        f"**{_RFI_SOURCE_LABEL.get(r.source, r.source)}** "
                        f"· weight {r.strength:.2f}"
                    )
                    st.markdown(r.statement)
                    st.caption(f"Cites: {r.cite()}")
                    st.markdown("")
        elif adj.verdict == "unverifiable":
            st.caption(
                "No probe can test this assertion — the evidence is silent either way. "
                "That is a reported outcome, not a pass."
            )
        st.markdown("")


_DECISION_OUTCOME_COLOR = {
    "continue": "#334155", "stop_cap": _RISK_GREY, "stop_frontier_exhausted": _RISK_GREY,
    "pull_second": "#334155", "single_match": _RISK_GREY, "no_match": _RISK_GREY,
    "recommend_re_rfi": "#f59e0b", "no_contradictions": "#16a34a",
    "not_applicable": _RISK_GREY,
    "sufficient": "#16a34a", "insufficient": "#f59e0b",
    "clears_bar": "#16a34a", "human_review": "#f59e0b",
}


def _render_decisions(res) -> None:
    st.subheader("Bounded decision trace")
    st.caption(
        "Every agentic decision is a deterministic rule over the evidence state — "
        "same case, same trace, every time — and each is stamped into the audit "
        "chain with its rationale and driving evidence. The agent proposes, "
        "surfaces, drafts, and flags; a human decides. "
        "See docs/agency-methodology.md."
    )

    if res.recidivism is not None:
        view = res.recidivism
        st.markdown("#### Case-graph memory at open")
        if view.is_recidivist:
            # The alert itself lives in the page header (shown once at case
            # open); this section carries the factual detail behind it.
            st.markdown(
                f"Recidivism surfaced at open: **{view.prior_review_count} prior "
                f"review(s)**, status `{view.account_status}` — prior cleared "
                "reviews do not exempt a subject (alert shown in the page header)."
            )
        else:
            st.caption(
                f"History clear at open: {view.prior_review_count} prior review(s), "
                f"status {view.account_status}."
            )
        if view.provenance:
            st.caption("source (prior_review_count, account_status): "
                       + "; ".join(view.provenance))
        if view.entity_overlaps:
            with st.expander(
                f"{len(view.entity_overlaps)} cross-case entity overlap(s) on record"
            ):
                for o in view.entity_overlaps:
                    st.markdown(f"- `{o.kind}` **{o.key}** seen in: {', '.join(o.case_ids)}")

    st.markdown("#### Decisions taken")
    for i, d in enumerate(res.decisions, start=1):
        color = _DECISION_OUTCOME_COLOR.get(d.outcome, _RISK_GREY)
        st.markdown(
            _chip(f"{i}. {d.decision_id}", "#475569") + " " + _chip(d.outcome, color),
            unsafe_allow_html=True,
        )
        st.markdown(d.plain_language)
        if d.rationale != d.plain_language:
            st.caption(f"Audit-exact rationale: {d.rationale}")
        st.caption(
            f"stamped in the audit chain: `agency/decision` · target `{d.decision_id}` "
            "(Audit trail tab)"
        )
        if d.provenance:
            st.caption("evidence rows: " + "; ".join(d.provenance))
        else:
            # Aggregate-input decisions cite no rows of their own — say why,
            # rather than showing a silent absence on a consequential decision.
            _NO_ROWS_WHY = {
                "sar_bar": (
                    "its input is the Critique, an aggregate whose row-level "
                    "basis is the draft's own cited claims (SAR draft tab)"
                ),
                "expand_hop": (
                    "the stop was driven by the cap/exhausted frontier, not "
                    "by new rows; prior hops' discoveries are cited above"
                ),
            }
            st.caption(
                "evidence rows: none of its own — "
                + _NO_ROWS_WHY.get(
                    d.decision_id,
                    "an aggregate-input decision; its basis is covered by the "
                    "cited aggregates' own audit stamps",
                )
                + "."
            )
        with st.expander("Driving evidence"):
            st.json(d.evidence)
        st.markdown("")

    if res.secondary_advisory is not None:
        st.markdown("#### Runner-up advisory (surfaced, not drafted)")
        st.info(
            f"`{res.secondary_advisory.advisory_id}` also passed the corroboration "
            "gate and is surfaced for analyst context. The SAR draft consumes the "
            "primary match alone."
        )
        _source_caption(res.secondary_advisory.provenance, prefix="match evidence")

    if res.rfi_followup is not None:
        st.markdown("#### Follow-up RFI worklist (prepared, never sent)")
        st.caption(
            "Discrete routine requests per contradicted claim — a worklist, not a "
            "letter. Assembly, sequencing, and sending are the analyst's decisions. "
            "Every request cites only the subject's own records and has passed the "
            "fail-closed anti-tipping-off screen; device-linked findings never "
            "generate subject-facing requests."
        )
        _REQUEST_KIND = {
            "transactions": "Transaction records request",
            "corporate_records": "Corporate documentation request",
            "prior_response": "Prior-response follow-up",
        }
        for q in res.rfi_followup.questions:
            st.markdown(f"**Claim {q.claim_id}** — rebutted by: {', '.join(q.sources)} "
                        "(analyst-only metadata)")
            if not q.requests:
                st.caption(
                    "No subject-facing request for this claim — its rebuttals are "
                    "internal-only surfaces (e.g. device linkage is never hinted at)."
                )
            for r in q.requests:
                st.markdown(f"- **{_REQUEST_KIND.get(r.kind, r.kind)}:** {r.text}")
                st.caption(f"cites (analyst-facing): {'; '.join(r.citations)}")
            if q.suppressed:
                st.warning(
                    f"{len(q.suppressed)} request(s) suppressed by the "
                    "anti-tipping-off screen and flagged for human authoring: "
                    f"{', '.join(q.suppressed)}."
                )


# Plain-language UI layer (Part I-B S4). Mirrors the DecisionRecord
# rationale/plain_language split (agency/decisions.py): the machine identifiers
# stay byte-unchanged in config, audit, tests, and provenance; the sweep view
# renders these compliance-officer forms keyed off them. The ONE deliberate
# exception is the provenance `source` column / `_source_caption`, which keep
# the real table names — they cite records, and a citation must name its store.
_ACTION_LABEL = {
    "proposes_designation_hold_review": "Propose designation hold review",
    "flags_reconciliation_gap": "Flag reconciliation gap",
    "flags_insider_staff_device_overlap": "Flag insider staff/device overlap (severe)",
    "proposes_confirm_existing_hold": "Confirm existing hold",
    "flags_foreign_signal_exposure_for_review": "Flag foreign-list signal exposure (review)",
    "flags_name_match_for_identity_review": "Flag name match — identity review",
    "flags_internal_tag_for_review": "Flag internal tag (review only)",
    "flags_for_review_non_flow_linkage": "Flag non-flow linkage (review only)",
}

# Hold-system machine names -> what the system IS, in plain terms.
_SYSTEM_LABEL = {
    "warehouse": "Compliance data feed (analytics copy)",
    "admin": "Account admin record (operational system)",
}

# Hold-status machine values -> plain language.
_HOLD_STATUS_LABEL = {
    "blocked": "Blocked",
    "no_hold": "No hold",
    "absent": "Absent (not in this system)",
}

# Escalation kind -> plain-language title.
_ESCALATION_KIND_LABEL = {
    "reconciliation_gap": "Hold-status reconciliation gap",
    "exposed_unblocked": "Exposed account with no hold on file",
    "foreign_signal_exposure": "Foreign-list signal exposure (review)",
}

# Draft status -> plain language (the only representable status is the draft one).
_ESCALATION_STATUS_LABEL = {
    "drafted_pending_human_review": "Drafted — pending human review (not sent)",
}

# Exposure-timing machine values -> plain language (Part I-B S3 fields).
_TIMING_LABEL = {
    "timeless_control": "Control (timeless)",
    "pre_designation": "Pre-designation",
    "post_designation": "Post-designation",
}

# KYC artifact machine names -> plain language (Part I-B S3 fields).
_ARTIFACT_LABEL = {
    "government_id": "Government ID",
    "proof_of_address": "Proof of address",
    "certificate_of_incorporation": "Certificate of incorporation",
    "beneficial_ownership": "Beneficial ownership",
}

# --- Part II identity-resolution plain-language maps (machine ids stay in
# provenance/citations; only the on-screen wording changes). -----------------

# Corroboration outcome -> compliance-officer wording (the dismissal is a
# feature: a same-name collision resolved to a different person).
_CORROBORATION_LABEL = {
    "corroborated_true_hit": "Corroborated — identity confirmed",
    "possible_match_needs_human": "Possible match — needs human review",
    "name_only_dismissed": "Dismissed — same-name collision (a different person)",
}

# Proximity signal id -> plain language. Calibrated throughout: these are
# CORRELATIONAL signals the ring surfaces, never assertions of kinship.
_PROXIMITY_SIGNAL_LABEL = {
    "shared_surname": "shares a surname/patronymic",
    "shared_kyc_attribute": "shares a KYC attribute (address/contact)",
    "declared_relationship": "declared relationship on file",
    "relationship_remark": "relationship-asserting remark",
    "shared_device": "shares a device",
    "email_handle_pattern": "shares an email-handle pattern",
    "kyc_document_cross_holding": "KYC-document cross-holding",
}

# Identity-review RFI status -> plain language (the only representable status).
_RFI_STATUS_LABEL = {
    "drafted_pending_human_review": "Drafted — pending human review (not sent)",
}

# Geo-triangulation plain language (Part III U3). Two-register throughout: plain
# phrasing on screen, the real table names kept in the provenance/citation
# captions (a citation must name its store). Calibrated: a signal *indicates
# possible presence*, it never *proves location*.
_GEO_SIGNAL_LABEL = {
    "ip_geolocation": "a login IP resolved inside the territory",
    "phone_prefix": "a registered phone carries the regional dialling prefix",
    "exclusive_carrier": "the number is on a region-only carrier",
    "kyc_geography": "a KYC document was issued inside the territory",
    "declared_residence": "declared residence is inside the territory",
    "device_timezone": "a device clock is set to the territory's timezone",
    "vpn_slip": "a territory IP appeared in a gap of continuous VPN use (VPN-slip)",
}

# Signal weight class -> how much a signal counts, in plain terms. A distinctive
# locator (a region-locked carrier, a VPN-slip) counts for more than an ordinary
# hit; a shared timezone is coarse.
_GEO_WEIGHT_LABEL = {
    "high_value": "distinctive (counts for more)",
    "standard": "standard",
    "weak": "coarse (counts for less)",
}

# The seven decide_geo_action outcomes -> plain proposal wording. Calibrated:
# every one is a *proposal drafted for an officer*, nothing is executed; the
# no_action outcome is a resolved review, never a silent dismissal (PM Rider A).
_GEO_PROPOSAL_LABEL = {
    "no_action_totality_resolves": "No restriction proposed — resolved review",
    "propose_edd_rfi": "Proposed — ask the customer (enhanced due-diligence RFI)",
    "propose_withdrawal_only_restriction": "Proposed — withdrawal-only restriction",
    "propose_trade_and_withdrawal_block": "Proposed — trade + withdrawal block",
    "propose_full_block_and_escalate": "Proposed — full block + escalate",
}

# Counter-evidence staleness -> plain counter-weight. Expiry is NEVER read as
# presence; it only degrades a document's weight AGAINST presence.
_GEO_STALENESS_LABEL = {
    "valid": "valid — argues against presence in full",
    "expired": "expired — still argues against presence, but its weight is degraded",
}

# Counterparty-designation lifecycle plain language (Part IV V2). Two-register:
# these render on screen; real table names stay in the provenance/citations.
#
# The reached lifecycle milestone -> plain wording. Calibrated: even the unblock
# terminal reads as a *proposal to lift*, never a done unblock (the register the
# PhRASING RIDER protects — see _CP_DISPOSITION_LABEL).
_CP_STATE_LABEL = {
    "exposure_detected": "exposure detected",
    "notification_drafted": "customer notification drafted",
    "acknowledgment_recorded": "acknowledgment recorded",
    "stop_dealing_verified": "stop-dealing verified",
    "unblock_proposed": "lifting the restriction proposed",
    "offboard_proposed": "offboarding proposed",
}

# The three decide_counterparty_lifecycle outcomes -> plain proposal wording.
# PHRASING RIDER (PM ruling, binding): propose_unblock renders as "Propose
# lifting the sweep-proposed restriction (pending human review)" — NEVER bare
# "propose unblock". These review-subject personas carry no visible hold row, so
# a bare "unblock" would leave a viewer asking what is being unblocked; naming it
# as the sweep-proposed restriction answers that on the surface itself. Every one
# is a REVIEW-tier proposal drafted for a human; no hold is ever mutated.
_CP_DISPOSITION_LABEL = {
    "propose_unblock": "Propose lifting the sweep-proposed restriction (pending human review)",
    "propose_offboard": "Propose offboarding the relationship (pending human review)",
    "hold_pending": "Hold retained pending review",
}


def _corroboration_label(outcome: str) -> str:
    return _CORROBORATION_LABEL.get(outcome, outcome)


def _proximity_signal_label(signal_id: str) -> str:
    return _PROXIMITY_SIGNAL_LABEL.get(signal_id, signal_id)


def _timing_label(timing) -> str:
    if not timing:
        return "—"
    return _TIMING_LABEL.get(timing, timing)


def _kyc_gap_label(missing) -> str:
    if not missing:
        return "—"
    return ", ".join(_ARTIFACT_LABEL.get(a, a) for a in missing)


def _system_label(name: str) -> str:
    return _SYSTEM_LABEL.get(name, name)


def _hold_label(status: str) -> str:
    return _HOLD_STATUS_LABEL.get(status, status)


def _gap_sentence(gap_type) -> str:
    """A reconciliation gap in a compliance officer's words (the published
    GAP_TAXONOMY), not the machine slug."""
    if not gap_type:
        return "—"
    return GAP_TAXONOMY.get(gap_type, gap_type)


def _render_identity_resolution(res, names) -> None:
    """Render the four Part-II identity-resolution capabilities that otherwise
    live only in the sweep result + audit chain: corroboration, the ownership/
    officer walk, the proximity ring, and the identity-review RFI. Two-register
    throughout — compliance-officer wording on screen, real table names in the
    provenance. Rendered only when a designation actually resolves an identity."""
    has_any = (res.corroboration or not res.ownership.is_empty()
               or not res.proximity.is_empty()
               or res.identity_rfis or res.suppressed_identity_rfis)
    if not has_any:
        return

    st.markdown("#### Identity resolution")
    st.caption(
        "Who might this designated party BE among our customers — resolved across "
        "name variants, corroborated against identity attributes, walked through "
        "corporate ownership, and ringed with relatives/associates. Everything "
        "here is **review-tier**: the sweep *surfaces* and *proposes*; a human "
        "resolves. No identity or kinship is asserted as fact."
    )

    # -- corroboration ------------------------------------------------------ #
    if res.corroboration:
        st.markdown("**Corroboration — name match vs. published identity details**")
        for c in res.corroboration:
            uid = c.evidence["candidate_uid"]
            st.markdown(
                f"- **uid {uid}** ({names.get(uid, uid)}): "
                f"**{_corroboration_label(c.outcome)}**. {c.plain_language}"
            )
            mism = c.evidence.get("mismatched_fields") or []
            if mism:
                st.caption("dismissed because these identifiers actively differ: "
                           + ", ".join(mism) + " (the dismissal reason, recorded)")
            if c.provenance:
                st.caption("source: " + "; ".join(c.provenance))

    # -- ownership + officer walk ------------------------------------------- #
    if not res.ownership.is_empty():
        own = res.ownership
        st.markdown(
            f"**Ownership & officer walk** — propagates designated status through "
            f"ownership at or above **{OWNERSHIP_CONTROL_THRESHOLD:.0%} control**; "
            "ownership/officer links carry **no flow exposure** (a distinct edge type)."
        )
        for p in own.propagations:
            st.markdown(
                f"- Company **uid {p.company_uid}** ({names.get(p.company_uid, p.company_uid)}) "
                f"is **{p.ownership_pct:.0%} owned/controlled** by resolved party "
                f"uid {p.owner_uid} ({names.get(p.owner_uid, p.owner_uid)}) — "
                "owned/controlled by a designated party (review)."
            )
            _source_caption(p.provenance)
        for f in own.fictitious_executives:
            st.markdown(
                f"- **Fictitious-executive flag**: officer of record "
                f"“{f.officer_name}” on company uid {f.company_uid} has no "
                "resolvable identity footprint (matches no account or KYC holder)."
            )
            _source_caption(f.provenance)
        for ch in own.control_changes:
            st.markdown(
                f"- **Post-designation control change**: appointment "
                f"{ch.appointment_id} on company uid {ch.company_uid} is dated "
                f"{ch.changed_date}, **after** the designation."
            )
            _source_caption(ch.provenance)

    # -- proximity ring ----------------------------------------------------- #
    if not res.proximity.is_empty():
        st.markdown(
            "**Proximity ring** — candidate relatives/associates of the resolved "
            "party, surfaced for **review with their signals**. Calibrated: a "
            "*possible* associate on a *correlational* signal, never asserted "
            "kinship; **not weighted by account activity** (dormancy is not innocence)."
        )
        for m in res.proximity.members:
            primary = ", ".join(_proximity_signal_label(s.signal_id)
                                for s in m.primary_signals)
            line = (f"- **uid {m.uid}** ({m.entity_name}) — candidate associate; "
                    f"signals: {primary}")
            if m.weighting_signals:
                line += (" · weighted by: "
                         + ", ".join(_proximity_signal_label(s.signal_id)
                                     for s in m.weighting_signals))
            line += f" · account status: {m.account_status}"
            st.markdown(line)
            _source_caption(m.provenance)

    # -- identity-review RFI ------------------------------------------------ #
    if res.identity_rfis or res.suppressed_identity_rfis:
        st.markdown("**Identity-review RFI — subject-facing, drafted never sent**")
        st.caption(
            "A routine identity/document-verification request to a customer the "
            "review could not resolve either way. Anti-tipping-off is enforced "
            "**fail-closed**: it reveals no match, method, list, or interest; a "
            "draft that trips the guard is suppressed and surfaced, never sent."
        )
        for r in res.identity_rfis:
            status = _RFI_STATUS_LABEL.get(r.status, r.status)
            with st.expander(f"{r.rfi_id} · uid {r.uid} ({r.subject_name}) · **{status}**"):
                st.write(r.text)
                st.caption("citations: " + "; ".join(r.citations))
        if res.suppressed_identity_rfis:
            st.warning(
                "**Suppressed identity-review drafts (surfaced, not sent):** "
                + "; ".join(f"uid {s.uid} — {s.reason}"
                            for s in res.suppressed_identity_rfis)
            )


def _render_geo_triangulation(res, names) -> None:
    """Render the Part-III geo-triangulation dossiers + proposals that otherwise
    live only in the sweep result + audit chain: per surfaced account, the
    location signals (with weight class), the VPN obfuscation markers, the
    counter-evidence + staleness, the KYC-refresh control gaps, the one-signal
    verdict, and the drafted (never sent) proposal — including the subject-facing
    EDD RFI text. Two-register throughout: compliance-officer wording on screen,
    real table names in the provenance. Rendered only for a TERRITORY designation
    (a designation of a geography, not a party — so there is no name screen)."""
    if not res.geo_dossiers:
        return

    st.markdown("#### Geo triangulation")
    st.caption(
        "This designation names a **territory**, not a person or company — so "
        "there is no name screen. Instead the sweep triangulates **possible "
        "presence** inside the sanctioned region from location signals, one "
        "account at a time. Everything here is **review-tier and calibrated**: a "
        "signal *indicates possible presence*, it never *proves location*; VPN use "
        "is an **obfuscation marker, never evidence**; document staleness never "
        "argues *for* presence. Every proposal is drafted for an officer — nothing "
        "is executed, no RFI is sent."
    )

    proposals = {p.uid: p for p in res.geo_proposals}
    # A compact roster line: each surfaced account and its proposal, plain.
    for d in res.geo_dossiers:
        p = proposals.get(d.uid)
        proposal_label = (_GEO_PROPOSAL_LABEL.get(p.outcome, p.outcome)
                          if p else "—")
        header = (f"uid {d.uid} ({names.get(d.uid, d.entity_name)}) · "
                  f"**{proposal_label}**")
        with st.expander(header):
            if p is not None:
                # N and its band, in plain terms (the analyst-facing decision text
                # is p.plain_language; the raw outcome slug never reaches screen).
                st.markdown(
                    f"**{proposal_label}** · net presence score **N = "
                    f"{p.net_presence_score}** "
                    f"({len(d.signals)} location signal(s) − counter-evidence)."
                )
                st.caption(p.plain_language)

            # -- location signals ------------------------------------------- #
            st.markdown("**Location signals** — each *indicates possible presence*, "
                        "never proof:")
            for s in d.signals:
                st.markdown(
                    f"- **{_GEO_SIGNAL_LABEL.get(s.signal_id, s.signal_id)}** · "
                    f"weight: {_GEO_WEIGHT_LABEL.get(s.weight_class, s.weight_class)} "
                    f"— {s.detail}"
                )
                _source_caption(s.provenance)

            # -- VPN markers (never location evidence) ---------------------- #
            if d.vpn_markers:
                st.markdown(
                    "**VPN / anonymising logins** — recorded as obfuscation "
                    "markers, **never as location evidence**:"
                )
                for m in d.vpn_markers:
                    st.markdown(f"- a VPN login at {m.timestamp}")
                    _source_caption(m.provenance)

            # -- counter-evidence + staleness ------------------------------- #
            if d.counter_evidence:
                st.markdown(
                    "**Counter-evidence** — documents arguing *against* presence; "
                    "staleness degrades their weight, and expiry is **never** read "
                    "as evidence of presence:"
                )
                for c in d.counter_evidence:
                    st.markdown(
                        f"- a {c.artifact_type} issued in {c.issuing_geography} — "
                        f"{_GEO_STALENESS_LABEL.get(c.staleness, c.staleness)}"
                    )
                    _source_caption(c.provenance)

            # -- control gaps (KYC-refresh; not a location signal) ---------- #
            if d.control_gaps:
                st.markdown(
                    "**Control gaps** — the exchange failed to re-verify a "
                    "document; surfaced for the control owner, **separately from "
                    "any location signal**:"
                )
                for g in d.control_gaps:
                    st.markdown(f"- {g.detail}")
                    _source_caption(g.provenance)

            # -- the one-signal-rule verdict -------------------------------- #
            # A plain restatement of dossier.note (which names raw signal ids as
            # analyst shorthand): the screen register stays plain, the machine
            # ids stay in the audit stamp.
            st.caption(
                f"Surfaced under the **one-signal rule**: {len(d.signals)} "
                "location signal(s) indicate possible presence. Signals are "
                "correlational and calibrated — presence is not asserted; a "
                "human resolves."
            )

            # -- the drafted (never sent) EDD RFI, or its suppression ------- #
            if p is not None and p.rfi_text:
                st.markdown(
                    "**Enhanced due-diligence RFI — subject-facing, "
                    f"{_RFI_STATUS_LABEL.get(p.status, p.status)}**"
                )
                st.caption(
                    "Anti-tipping-off is enforced **fail-closed** on the rendered "
                    "text: it reveals no territory, match, method, list, or "
                    "interest; a draft that trips the guard is suppressed and "
                    "surfaced, never sent."
                )
                st.write(p.rfi_text)
                st.caption("citations: " + "; ".join(p.citations))
            elif p is not None and p.rfi_suppressed_reason:
                st.warning(
                    "**EDD RFI suppressed (surfaced, not drafted):** "
                    + p.rfi_suppressed_reason
                )

    st.caption(
        f"Geo-triangulation methodology v{GEO_VERSION} · signals indicate "
        "possible presence, never prove location · proposals are drafted for a "
        "human, never executed."
    )


def _render_counterparty_lifecycle(res, names) -> None:
    """Render the Part-IV counterparty-designation lifecycle that otherwise lives
    only in the sweep result + audit chain: per customer who dealt with the
    designated counterparty AFTER it was designated, the reached lifecycle state,
    the drafted (never sent) customer notification, and the relationship
    disposition (propose lifting the restriction / offboard / hold). Two-register
    throughout: compliance-officer wording on screen, real table names in the
    provenance. Rendered ONLY for a ``counterparty_service`` designation (a
    designated VASP/exchange whose hosted wallets our customers dealt with) — the
    only designation kind that runs a relationship lifecycle.

    THE HARD RULE is stated on the surface itself: no hold is ever mutated; an
    unblock is a PROPOSAL to lift the sweep-proposed restriction, drafted for a
    human, never executed."""
    if res.designation.list_type != "counterparty_service":
        return
    if not (res.lifecycle_dispositions or res.counterparty_notifications
            or res.suppressed_counterparty_notifications):
        return

    st.markdown("#### Counterparty-designation lifecycle")
    st.caption(
        "This designation names a **counterparty service** — a designated "
        "exchange/VASP whose hosted wallets our customers dealt with. Detection "
        "is already done above; this is what happens **after**: the relationship "
        "lifecycle for each customer who dealt with the counterparty **after it "
        "was designated**. Everything here is **review-tier** — the sweep drafts "
        "a customer notification and *proposes* a relationship disposition; a "
        "person decides and acts. **No hold is ever lifted here:** an unblock "
        "exists only as a proposal for a reviewer to apply, never an automatic "
        "action."
    )

    notes = {n.uid: n for n in res.counterparty_notifications}
    for d in sorted(res.lifecycle_dispositions, key=lambda x: x.uid):
        disposition = _CP_DISPOSITION_LABEL.get(d.outcome, d.outcome)
        with st.expander(f"uid {d.uid} ({names.get(d.uid, d.uid)}) · **{disposition}**"):
            # -- the reached lifecycle state, plain ------------------------- #
            st.markdown(
                f"**Lifecycle state:** {_CP_STATE_LABEL.get(d.state, d.state)}"
            )

            # -- the disposition + its plain rationale ---------------------- #
            # The screen shows the plain proposal label + the decision's
            # plain_language gloss; the raw outcome slug never reaches the screen.
            st.markdown(f"**Proposed disposition — {disposition}**")
            st.caption(d.decision.plain_language)
            st.markdown(
                "- acknowledgment on file: "
                f"**{'yes' if d.acknowledged else 'no'}**\n"
                "- stopped dealing since acknowledging: "
                f"**{'verified' if d.stop_verified else 'not verified'}**\n"
                "- prior acknowledged designated counterparty (repeat): "
                f"**{'yes' if d.repeat_offender else 'no'}**"
            )
            if d.prior_acknowledged_counterparties:
                st.caption(
                    "prior acknowledged counterparty designation(s): "
                    + ", ".join(d.prior_acknowledged_counterparties)
                )
            _source_caption(d.provenance)

            # -- the drafted (never sent) customer notification ------------- #
            n = notes.get(d.uid)
            if n is not None:
                st.markdown(
                    "**Customer notification — subject-facing, "
                    f"{_RFI_STATUS_LABEL.get(n.status, n.status)}**"
                )
                st.caption(
                    "A Terms-and-Conditions notification, authored **guard-safe** "
                    "and validated fail-closed on the rendered text: it names the "
                    "counterparty's public designation and the customer's "
                    "contractual obligation, and reveals no evidence method, no "
                    "investigation, and no law-enforcement interest. Drafted for a "
                    "human — there is no send path."
                )
                st.write(n.text)
                st.caption("citations: " + "; ".join(n.citations))

    # Suppressed notifications — surfaced with the reason, never silently dropped.
    for s in res.suppressed_counterparty_notifications:
        st.warning(
            "**Customer notification suppressed (surfaced, not drafted)** for uid "
            f"{s.uid} ({names.get(s.uid, s.uid)}): {s.reason}"
        )

    st.caption(
        f"Counterparty-lifecycle policy · agency methodology v{AGENCY_VERSION} · "
        "dispositions are REVIEW-tier proposals drafted for a human · no hold is "
        "mutated — an unblock proposes lifting the sweep-proposed restriction, "
        "never applies it."
    )


def _example_designation_payloads() -> tuple[str, str]:
    """The two one-click example payloads for the simulated list-feed box.

    The VALID payload is serialized FROM a constructed :class:`Designation`, so it
    is schema-valid by construction and can never silently drift from the model
    again: a new required field breaks this constructor loudly (at demo/test time),
    rather than leaving a stale, invalid example sitting in the box. The MALFORMED
    payload omits required fields, so a visitor can trigger the fail-closed
    rejection deliberately. All values are obviously synthetic."""
    valid = Designation(
        designation_id="DES-2026-9001",
        designated_name="Example Shell Trading",
        program="SYNTHETIC-IRGC-STYLE",
        entity_type="company",
        designated_addresses=["T9syntheticExampleAddr000"],
        designation_date="2026-02-01",
        source_regime="SYNTHETIC-OFAC-STYLE",
        list_type="sdn_style",
        obligation_vs_signal="obligation",
        listed_since="2026-02-01",
    )
    valid_json = json.dumps(valid.model_dump(), indent=2)
    # Deliberately missing every field but two → fails the fail-closed validator.
    malformed_json = json.dumps({
        "designation_id": "DES-2026-9002",
        "designated_name": "Broken Example Corp",
    }, indent=2)
    return valid_json, malformed_json


def _render_sweep_mode(conn: Connectors) -> None:
    """Designation-triggered remediation sweep — the ledger-wide second entry
    point. No subject selector: the sweep runs over the whole ledger from a
    picked synthetic designation or a simulated inbound list-feed payload,
    surfaces exposed accounts + reconciliation gaps, and drafts (never sends)
    escalations."""
    st.subheader("Designation-triggered remediation sweep")
    st.caption(
        "A second entry point over the finished core: input a synthetic "
        "OFAC-style designation and sweep the **whole ledger** for directly and "
        "indirectly exposed accounts, reconcile hold status across two mock "
        "systems, and produce a grounded remediation worksheet. The sweep "
        "*surfaces*, *proposes*, and *flags* — a human remediates. No status is "
        "changed; escalations are drafted, never sent."
    )

    designations = conn.all_designations()
    labels = {
        d["designation_id"]: f"{d['designation_id']} — {d['designated_name']}"
        for d in designations
    }
    ids = [d["designation_id"] for d in designations]

    with st.sidebar:
        st.header("Designation")
        source = st.radio(
            "Source",
            ["Synthetic list", "Simulate list-feed update (advanced)"],
            key="sweep_source",
        )

    designation = None
    if source == "Synthetic list":
        chosen = st.sidebar.selectbox(
            "Designation", ids,
            format_func=lambda i: labels.get(i, i), key="sweep_designation_id",
        )
        rec = conn.get_designation(chosen)
        designation = designation_from_record(rec)
    else:
        # The paste box is a MANUAL STAND-IN for a list-feed event: in production
        # the payload arrives from an external source (a vendor screening API, a
        # parsed OFAC-style list file, or an internal list-management system) and
        # hits Okojo's ingestion boundary. This simulates that inbound payload.
        valid_payload, malformed_payload = _example_designation_payloads()
        st.sidebar.caption(
            "In production, designations arrive as structured payloads from a "
            "sanctions-list feed or vendor API. This box simulates that inbound "
            "event. All payloads, real or simulated, pass the same fail-closed "
            "validation before anything runs."
        )
        # Seed the box with the valid example on first render; the two buttons
        # overwrite it with one click (no typing). Setting the text_area's own
        # session_state key BEFORE the widget is instantiated is the supported
        # Streamlit pattern — the text_area then reads it, so no value= is passed.
        if "sweep_paste" not in st.session_state:
            st.session_state["sweep_paste"] = valid_payload
        if st.sidebar.button("Load valid example payload", key="sweep_load_valid"):
            st.session_state["sweep_paste"] = valid_payload
        if st.sidebar.button("Load malformed example payload",
                             key="sweep_load_malformed"):
            st.session_state["sweep_paste"] = malformed_payload
        raw = st.sidebar.text_area(
            "Inbound designation payload (JSON)", height=240, key="sweep_paste",
        )
        try:
            designation = parse_designation(raw)
        except DesignationParseError as exc:
            st.error(
                "**Designation rejected (fail-closed).** Nothing was written — "
                "parsing is a pure function; a malformed payload leaves no chain "
                f"and no directory.\n\n```\n{exc}\n```"
            )
            return

    res = run_sweep(designation, conn=conn)

    d = res.designation
    st.markdown(
        f"**{d.designation_id}** · {d.designated_name} · program `{d.program}` · "
        f"{len(d.designated_addresses)} designated address(es), "
        f"{len(res.exposure.addresses_in_ledger)} in-ledger."
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Exposed accounts", len(res.exposure.exposed))
    c2.metric("Direct", len(res.exposure.direct_uids()))
    c3.metric("Adjacent (review)", len(res.exposure.adjacent))
    c4.metric("Hold-status gaps", len(res.gaps))
    c5.metric("Escalations drafted", len(res.escalations))

    if not res.exposure.exposed and not res.name_matches:
        st.success(
            "No exposure and no name match: this designation touches nothing in "
            "the ledger — the false-positive probe returns cleanly, no fabricated "
            "hits, chain verified."
        )

    names = {a["uid"]: a["entity_name"] for a in conn.all_accounts()}

    # -- worksheet ---------------------------------------------------------- #
    st.markdown("#### Remediation worksheet")
    st.caption(
        "One row per surfaced account, in triage order (most severe action "
        "first). Every row is grounded: the sweep fails closed rather than emit "
        "a row it cannot cite. A privileged/internal tag is **flagged for "
        "review, never obeyed.**"
    )
    if res.worksheet:
        ws_df = pd.DataFrame([
            {
                "uid": r.uid,
                "account": names.get(r.uid, r.entity_name),
                "recommended action": _ACTION_LABEL.get(
                    r.recommended_action, r.recommended_action),
                # Uniform string so the column has one Arrow type (adjacency
                # rows carry no hop distance).
                "hops": "—" if r.hops is None else str(r.hops),
                "direct": "✓" if r.direct else "",
                "exposure (USDT)": f"{r.exposure_usdt:,.0f}" if r.exposure_usdt else "—",
                "exposure timing": _timing_label(r.exposure_timing),
                "KYC gap": _kyc_gap_label(r.kyc_missing_artifacts),
                _SYSTEM_LABEL["warehouse"]: _hold_label(r.warehouse_status),
                _SYSTEM_LABEL["admin"]: _hold_label(r.admin_status),
                "reconciliation gap": _gap_sentence(r.gap_type),
                "internal tag": "⚑" if r.internal_tag_flag else "",
                "source": _cites(r.provenance),
            }
            for r in res.worksheet
        ])
        st.dataframe(ws_df, use_container_width=True, hide_index=True)
    else:
        st.info("No accounts surfaced for this designation.")

    # -- identity resolution (Part II) -------------------------------------- #
    _render_identity_resolution(res, names)

    # -- geo triangulation (Part III) --------------------------------------- #
    _render_geo_triangulation(res, names)

    # -- counterparty-designation lifecycle (Part IV) ----------------------- #
    _render_counterparty_lifecycle(res, names)

    # -- hold-status reconciliation ----------------------------------------- #
    st.markdown("#### Hold-status reconciliation")
    st.caption(
        f"Two mock systems: the **{_SYSTEM_LABEL['admin']}** vs. the "
        f"**{_SYSTEM_LABEL['warehouse']}**. The sweep reconciles the full ledger; "
        "a gap is flagged with both rows cited (the documented data-integrity "
        "failure mode)."
    )
    if res.gaps:
        for g in res.gaps:
            st.markdown(
                f"- **uid {g.uid}** ({names.get(g.uid, g.uid)}): "
                f"{_SYSTEM_LABEL['warehouse']} — **{_hold_label(g.warehouse_status)}** "
                f"vs {_SYSTEM_LABEL['admin']} — **{_hold_label(g.admin_status)}**: "
                f"{_gap_sentence(g.gap_type)}"
            )
            _source_caption(g.provenance)
    else:
        st.success("No reconciliation gaps: the two systems agree across the ledger.")

    # -- escalation drafts -------------------------------------------------- #
    st.markdown("#### Escalation drafts")
    st.caption(
        "Internal-to-compliance drafts prepared for the human remediation owner "
        "— **drafted, never sent** (no send path exists). Each passed the "
        "grounding, resolvability, and calibrated-language checks; a draft that "
        "fails any check is suppressed and surfaced with its reason, never "
        "silently dropped."
    )
    for e in res.escalations:
        kind = _ESCALATION_KIND_LABEL.get(e.kind, e.kind)
        status = _ESCALATION_STATUS_LABEL.get(e.status, e.status)
        with st.expander(f"{e.escalation_id} · {kind} · uid {e.uid} · **{status}**"):
            st.markdown(f"**{e.subject}**")
            st.write(e.body)
            st.caption("citations: " + "; ".join(e.citations))
    if res.suppressed_escalations:
        st.warning(
            "**Suppressed drafts (surfaced, not sent):** "
            + "; ".join(
                f"uid {s.uid} ({_ESCALATION_KIND_LABEL.get(s.kind, s.kind)}) — {s.reason}"
                for s in res.suppressed_escalations)
        )
    elif not res.escalations:
        st.info("No escalations drafted for this designation.")

    # -- package + audit ---------------------------------------------------- #
    st.markdown("#### Decision-ready package & audit trail")
    if res.package_path and res.package_path.exists():
        st.download_button(
            "Download remediation package (JSON)",
            data=res.package_path.read_bytes(),
            file_name=f"{d.designation_id}_sweep_package.json",
            mime="application/json",
        )
        st.caption(
            f"Package SHA-256 `{res.package_sha256[:16]}…` is stamped into the "
            f"sweep's own hash chain · chain verified: "
            f"**{res.audit_verified}** · {len(res.audit_records)} records."
        )

    # Reviewable, not just provable: the Audit Narrator reads this sweep's own
    # chain and renders it in plain language (Phase 9). Read-only — it writes
    # nothing to the chain.
    _render_audit_narrative(res.audit_records, family="sweep",
                            subject=d.designation_id)

    with st.expander("Audit trail (this sweep's own tamper-evident chain)"):
        audit_df = pd.DataFrame([
            {"seq": r["seq"], "actor": r["actor"], "action": r["action"],
             "target": r.get("target") or "", "hash": r["hash"][:12] + "…"}
            for r in res.audit_records
        ])
        st.dataframe(audit_df, use_container_width=True, hide_index=True)
    st.caption(
        f"Sweep methodology v{SWEEP_VERSION} · identity resolution "
        f"v{IDENTITY_VERSION} · money-flow edges: control links and value "
        f"transfers · name-match threshold {sweep_config()['name_match_threshold']}."
    )


def _render_audit_narrative(records, *, family: str, subject=None) -> None:
    """Render the read-only Audit Narrator's two-register narrative over one
    hash chain: plain sentences on screen, the cited ``(seq, hash)`` provenance
    kept in an expander.

    The narrator is grounded and read-only — it writes nothing, and every
    sentence cites the exact record it reads. Setup records (tool calls, the
    versioned ``*_config`` stamps) render de-emphasized; consequential actions
    render prominent; a chain that fails verification renders its break report
    and nothing past it. Degrades to a caption rather than aborting the surface
    if narration cannot run (the reliability discipline: a reading aid never
    takes the audit tab down)."""
    try:
        nar = narrate_chain(records, family=family, subject=subject)
    except Exception:  # pragma: no cover - narrator is fail-closed; the UI must not abort
        st.caption("Audit narrative unavailable for this chain.")
        return

    st.markdown(
        f"**Plain-language narrative** — read-only, grounded, narrator "
        f"v{NARRATOR_VERSION}. Each line is numbered by its record's `seq` in the "
        f"chain below, so a sentence and the raw record it reads carry the same "
        f"number; every sentence cites that record (provenance in the expander)."
    )
    for s in nar.sentences:
        # Number every line by the record's own seq so the narrative and the raw
        # hash chain line up one-to-one (a broken chain shows a single break line
        # numbered at the record where verification first failed). The number is
        # bold-formatted (`**n.**`, never a bare `n. `) so Markdown renders it as
        # literal text rather than swallowing it into an auto-numbered list.
        n = s.ref.seq
        if s.register == "break":
            st.error(f"**{n}.** {s.text}")
        elif s.register == "setup":
            st.caption(f"**{n}.** · {s.text}")
        else:
            st.markdown(f"**{n}.** {s.text}")

    with st.expander("Narrative provenance (each sentence's cited record)"):
        st.dataframe(
            pd.DataFrame([
                {"line": i + 1, "register": s.register, "seq": s.ref.seq, "hash": s.ref.hash}
                for i, s in enumerate(nar.sentences)
            ]),
            use_container_width=True, hide_index=True,
        )


def main() -> None:
    st.markdown(
        "<h1 style='font-size:1.6rem;font-weight:700;margin:0 0 0.25rem;'>"
        "Okojo — Agentic Crypto-Investigations Co-Pilot</h1>",
        unsafe_allow_html=True,
    )
    st.caption(f"{_PHASE} · **fully synthetic data** · a human reviews, decides, and files.")

    try:
        conn = get_connectors()
    except FileNotFoundError as exc:
        st.error(f"{exc}")
        st.info("Run `python scripts/generate_scenario.py` to create the synthetic dataset, then reload.")
        return

    # Mode switch (not a tab): a per-subject case investigation vs. the
    # ledger-wide designation sweep. The logo renders once here, above the
    # switch, so neither mode re-renders it.
    with st.sidebar:
        _, _logo_col, _ = st.columns([7, 10, 7])
        _logo_col.image(_LOGO_PATH, use_container_width=True)
        mode = st.radio(
            "Mode", ["Case investigation", "Designation sweep"], key="app_mode",
        )
        st.markdown("---")
    if mode == "Designation sweep":
        _render_sweep_mode(conn)
        return

    accounts = conn.all_accounts()
    # One role vocabulary everywhere: the selector shows the same human-readable
    # role labels as the roster cards (never the raw machine codes).
    label_for = {
        a["uid"]: (
            f"{a['entity_name']}  —  uid {a['uid']}  "
            f"({_ROLE_LABEL.get(a['role_in_ring'], a['role_in_ring'])})"
        )
        for a in accounts
    }

    # Subject is the single source of truth in session state; the sidebar selector
    # and the roster's "Investigate" buttons both drive it. Default to the
    # licensed-trust intermediary (the RFI subject that exercises every stage).
    default_uid = next(
        (a["uid"] for a in accounts if a["role_in_ring"] == "licensed_trust_intermediary"),
        accounts[0]["uid"],
    )
    if "subject_uid" not in st.session_state:
        st.session_state.subject_uid = default_uid

    # Dropdown lists the non-noise ring, plus the current subject if it isn't one
    # (e.g. a noise account reached in the graph and picked from the roster), so
    # the selector always reflects who is under investigation.
    ring = sorted(
        (a for a in accounts if a["role_in_ring"] != "noise"),
        key=lambda a: a["role_in_ring"],
    )
    option_uids = [a["uid"] for a in ring]
    if st.session_state.subject_uid not in option_uids:
        option_uids.append(st.session_state.subject_uid)

    with st.sidebar:
        # The logo and mode switch are already rendered above; this block adds
        # the case-mode-only selector.
        st.header("Case selector")
        st.selectbox(
            "Subject",
            option_uids,
            format_func=lambda uid: label_for.get(uid, f"uid {uid}"),
            key="subject_uid",
        )
        max_hops = st.slider("Network expansion hops", 1, 7, 2)
        st.markdown("---")
        st.markdown(
            "**Reminder:** the agent *proposes, surfaces, drafts, and flags*. "
            "A privileged/internal tag is **flagged for review, never obeyed**."
        )

    subject_uid = st.session_state.subject_uid
    res = run_case(subject_uid, conn=conn, max_hops=max_hops)

    # -- header metrics ---------------------------------------------------- #
    # The Advisory tile carries the one long value in the row (an advisory id
    # like "FIN-2025-A002"), so it gets double weight to render untruncated.
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 2])
    expansion_summary = res.expansion.summary()
    c1.metric("Anomalies", len(res.profile.anomalies))
    c2.metric("Network reached", expansion_summary["accounts_reached"])
    c3.metric("Sanctioned reached", expansion_summary["sanctioned_addresses_reached"])
    c4.metric("Tells", len(res.tells))
    c5.metric("Watchlist hits", len(res.alias_hits))
    c6.metric("Advisory", res.advisory.advisory_id if res.advisory else "—")
    st.caption(
        "Anomalies / Network / Sanctioned / Advisory are subject-scoped; **Tells and "
        "Watchlist hits are dataset-wide screens** (they run over every remark and "
        "account name, not just this subject's). Each count decomposes in its tab "
        "with row-level citations."
    )

    subject_account = conn.get_account(subject_uid)
    if res.profile.internal_tag:
        st.warning(
            f"Internal 'do-not-block' tag present: {res.profile.internal_tag!r} — "
            "**flagged for review, not obeyed.**"
        )
        _source_caption(subject_account.provenance if subject_account else None)

    if res.recidivism is not None and res.recidivism.is_recidivist:
        st.error(
            f"**Recidivism surfaced at case open:** {res.recidivism.prior_review_count} "
            f"prior review(s), status `{res.recidivism.account_status}` — prior cleared "
            "reviews do not exempt a subject. Surfaced for human review "
            "(details in the Decisions tab)."
        )
        if res.recidivism.provenance:
            st.caption("source (prior_review_count, account_status): "
                       + "; ".join(res.recidivism.provenance))

    names = {a["uid"]: a["entity_name"] for a in accounts}

    (tab_sanctions, tab_timeline, tab_network, tab_tells, tab_rfi,
     tab_advisory, tab_decisions, tab_sar, tab_audit) = st.tabs(
        ["Sanctions", "Timeline", "Network", "Tells", "RFI", "Advisory",
         "Decisions", "SAR draft", "Audit trail"]
    )

    # -- Sanctions (gating control: watchlist name-match + on-chain exposure) -- #
    with tab_sanctions:
        st.subheader("Sanctions & watchlist screening")
        st.caption(
            "The gating compliance control, checked first: does any account match a "
            "sanctions/watchlist name, and do any account's funds reach a synthetic "
            "sanctioned endpoint? Two faces of the same question — a name match and a "
            "fund-flow match."
        )

        st.markdown("#### Watchlist name screening")
        st.caption(
            "Account names fuzzy-matched (RapidFuzz) against the synthetic SDN/alias list. "
            "Transliteration variants are caught where exact-match screening would miss them; "
            "unrelated decoys are not. A hit is a name-similarity flag for human review — "
            "not a confirmed identity match."
        )
        if res.alias_hits:
            adf = pd.DataFrame([
                {"uid": str(h.uid), "entity_name": h.entity_name, "matched_alias": h.matched_alias,
                 "sdn_id": h.sdn_id, "score": h.score, "program": h.program,
                 "source": _cites(h.provenance)}
                for h in res.alias_hits
            ])
            st.dataframe(adf, use_container_width=True, hide_index=True)
            with st.expander("How the name match works — show the math"):
                st.markdown(
                    f"**Algorithm:** RapidFuzz `WRatio` (a weighted character/token "
                    f"similarity, 0–100). **Threshold:** a score **≥ {SCREEN_THRESHOLD}** "
                    "is surfaced for review — transliteration variants score ~90+, "
                    "unrelated decoys sit well below."
                )
                st.markdown(
                    "The score is a **name-similarity confidence for human review — "
                    "not a confirmed identity match, and not a risk score.** "
                    "A “92”, for instance, means the two strings are 92/100 similar "
                    "(a reason to *look*), nothing more. A person adjudicates."
                )
                for h in res.alias_hits:
                    name_html, alias_html = _diff_html(h.entity_name, h.matched_alias)
                    st.markdown(
                        f"<div style='margin:6px 0;font-size:0.9rem;'>"
                        f"uid {h.uid} · similarity <b>{h.score:.0f}</b> / 100 "
                        f"(threshold {SCREEN_THRESHOLD}) · program {h.program}<br>"
                        f"account name:&nbsp;&nbsp;{name_html}<br>"
                        f"watchlist alias: {alias_html}<br>"
                        f"<span style='color:{_RISK_GREY};font-size:0.78rem;'>"
                        f"source: {_cites(h.provenance)}</span></div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No watchlist name hits across the dataset.")

        st.markdown("---")
        st.markdown("#### On-chain sanctioned exposure")
        st.caption(
            "Graded exposure to the synthetic sanctioned set by tainted amount and hop "
            "distance (money-flow path only). Bands: high ≥ 0.60, medium 0.30–0.60. "
            "Every score decomposes into named factors — expand *show the math* below."
        )
        if res.risk.scores:
            rdf = pd.DataFrame([
                {"uid": str(s.uid), "name": names.get(s.uid, s.uid), "score": s.score,
                 "band": s.band, "hops_to_sanctioned": s.hop_distance,
                 "tainted_usdt": s.tainted_amount_usdt, "reasons": ", ".join(s.reasons),
                 "money_flow": s.exposure_path, "source": _cites(s.provenance)}
                for s in res.risk.scores
            ])
            st.dataframe(rdf, use_container_width=True, hide_index=True)

            with st.expander("Score breakdown — show the math (per account)"):
                st.caption(
                    "Each score is a transparent product of an **amount** factor "
                    "(tainted value on a fixed log scale) and a **proximity** factor "
                    "(per-hop decay). Gas-only rows use a fixed gas-base instead of amount."
                )
                for s in res.risk.scores:
                    d = s.decomposition
                    st.markdown(
                        f"**uid {s.uid}** · {names.get(s.uid, s.uid)} · _{d.kind}_  \n"
                        f"`{d.formula}`  → **{s.score:.3f}** ({s.band})"
                    )

            with st.expander("Provenance (per scored account)"):
                for s in res.risk.scores:
                    st.caption(f"uid {s.uid}: " + "; ".join(p.cite() for p in s.provenance))

            with st.expander(f"Scoring methodology & version (v{SCORING_VERSION})"):
                cfg = scoring_config()
                st.markdown(
                    f"Methodology **v{cfg['version']}**, stamped into the audit trail for "
                    "reproducibility. These are **tunable policy parameters, not universal "
                    "constants** — full rationale in `docs/scoring-methodology.md`."
                )
                st.markdown(
                    f"- **Membership edges:** `{', '.join(cfg['membership_edge_types'])}` "
                    "(gas/relationship edges excluded from the fund-flow metric)\n"
                    f"- **Per-hop decay:** `{cfg['decay']}`  ·  **amount floor:** "
                    f"`{cfg['floor']}`  ·  **saturates at:** ${cfg['amount_ref_usdt']:,.0f}\n"
                    f"- **Bands:** high ≥ `{cfg['band_high']:.2f}`, medium ≥ "
                    f"`{cfg['band_medium']:.2f}`  ·  **gas-base:** `{cfg['gas_base']}`"
                )
        else:
            st.info("No on-chain sanctioned exposure for this cluster.")

    # -- Timeline ---------------------------------------------------------- #
    with tab_timeline:
        st.subheader(f"{res.subject_name} — anomaly-flagged timeline")
        if res.profile.anomalies:
            for a in res.profile.anomalies:
                color = _SEVERITY_COLOR.get(a.severity, "#6b7280")
                st.markdown(
                    f"<span style='color:{color};font-weight:600'>[{a.severity.upper()}] "
                    f"{a.code}</span> — {a.statement}",
                    unsafe_allow_html=True,
                )
                st.caption("source: " + "; ".join(p.cite() for p in a.provenance))
        else:
            st.info("No anomalies surfaced for this subject.")
        st.markdown("---")
        st.markdown("#### Chronology")
        st.caption(
            "Every event in the unified subject timeline, in order, each citing its "
            "source row. Events that triggered an anomaly above carry that anomaly "
            "pinned inline, so the flag and the moment it fired stay together."
        )
        # Pin anomalies onto the events that triggered them: an anomaly and its
        # triggering event cite the same evidence rows, so pointer intersection
        # is the join (no heuristics, no new model fields).
        anomaly_pins: dict[str, list] = {}
        for a in res.profile.anomalies:
            for p in a.provenance:
                anomaly_pins.setdefault(p.cite(), []).append(a)
        month = None
        for e in res.profile.events:
            m = str(e.timestamp)[:7]
            if m != month:
                month = m
                st.markdown(f"**{month}**")
            label, color = _EVENT_KIND_STYLE.get(e.kind, (e.kind, _RISK_GREY))
            pinned = {
                a.code: a for p in e.provenance for a in anomaly_pins.get(p.cite(), [])
            }
            pins = "".join(
                _chip(
                    f"⚑ {_ANOMALY_LABEL.get(code, code)}",
                    _SEVERITY_COLOR.get(a.severity, _RISK_GREY),
                )
                for code, a in pinned.items()
            )
            st.markdown(
                f"{_chip(label, color)} "
                f"<span style='color:{_RISK_GREY};font-size:0.8rem;'>"
                f"{str(e.timestamp)[11:16]} · {str(e.timestamp)[:10]}</span> "
                f"— {e.description} {pins}",
                unsafe_allow_html=True,
            )
            st.caption("source: " + "; ".join(p.cite() for p in e.provenance))
        with st.expander("Raw event table"):
            ev = pd.DataFrame([
                {"timestamp": e.timestamp, "kind": e.kind, "event": e.description,
                 "source": _cites(e.provenance)}
                for e in res.profile.events
            ])
            st.dataframe(ev, use_container_width=True, hide_index=True)

    # -- Network ----------------------------------------------------------- #
    with tab_network:
        st.subheader("Network expansion")
        st.caption(
            "Gold ★ = subject · red ▲ = synthetic-sanctioned endpoint · orange = ring account · "
            "blue = address. Edges: purple = shared device, green = reused KYC, red dashed = gas-funding."
        )
        expand_stop = next(
            (d for d in reversed(res.decisions) if d.decision_id == "expand_hop"),
            None,
        )
        if expansion_summary["edges"] == 0:
            st.info(
                "This subject is isolated at the configured hop depth: no shared "
                "devices, no reused KYC documents, no gas-funding links, and no "
                "transaction counterparties reached. The graph shows the subject "
                "node alone — an honest empty result, not a rendering failure."
            )
        elif expand_stop is not None and expand_stop.outcome == "stop_frontier_exhausted":
            hops_done = expand_stop.evidence.get("hops_done")
            st.info(
                f"Expansion stopped at hop {hops_done} of the requested "
                f"{max_hops} — no further connections found beyond that point. "
                "The graph is complete at this depth, not truncated "
                "(recorded in the Decisions tab as `stop_frontier_exhausted`)."
            )
        if res.graph_html_path and Path(res.graph_html_path).exists():
            components.html(Path(res.graph_html_path).read_text(encoding="utf-8"), height=760, scrolling=True)
        elif res.render_error:
            st.warning(
                "Graph rendering failed for this run — the case completed without it, "
                "and the failure is recorded in the audit trail "
                "(`network_expander/graph_render_failed`). Error: "
                f"`{res.render_error}`"
            )
        else:
            st.info("Graph not rendered.")

        # -- gas-funding collapse callout ---------------------------------- #
        gas_links = res.expansion.gas_funding_links
        if gas_links:
            controllers = sorted({l["controller_uid"] for l in gas_links})
            who = ", ".join(f"uid {c} · {names.get(c, c)}" for c in controllers)
            st.warning(
                f"**Gas-funding collapse** — {len(gas_links)} “non-custodial” hop(s) "
                f"attributed to their gas funder ({who}). A wallet is not independent of "
                "whoever pays its gas."
            )
            gdf = pd.DataFrame([
                {"funder_address": l["funder_address"], "funded_address": l["funded_address"],
                 "controller_uid": str(l["controller_uid"]),  # uid is an identifier, not a quantity
                 "source": l["provenance"].cite()}  # the expander's own evidence row
                for l in gas_links
            ])
            st.dataframe(gdf, use_container_width=True, hide_index=True)
        else:
            st.caption("No gas-funding links surfaced in this cluster.")

        st.markdown("---")
        st.markdown("#### Connected accounts — triage roster")
        st.caption(
            "Every connected account is a potential case of its own. Sorted by risk "
            "(subject pinned first). **Investigate →** reloads the whole case on that "
            "account. *Case file on record* means a prior run exists on disk — not a "
            "live case-management status."
        )
        risk_by_uid = {s.uid: s for s in res.risk.scores}
        cases_dir = default_out_dir(subject_uid).parent
        roster = build_roster(conn, res.expansion, cases_dir,
                              store=CaseGraphStore(cases_dir / "case_graph.sqlite"))
        _render_roster(roster, risk_by_uid)

    # -- Tells ------------------------------------------------------------- #
    with tab_tells:
        st.subheader("Remark tells")
        st.caption(
            "Free-text transaction remarks fuzzy-matched (RapidFuzz) against "
            "curated control/illicit phrases (*illicit_phrase*) and the case's own "
            "entity-name tokens (*control_alias* — a remark naming a controller is "
            "an attribution tell). **This screen runs over every remark in the "
            "dataset, not just this subject's transactions** — attribution often "
            "breaks open on someone else's remark. Each hit is a flag for human "
            "review, never a determination."
        )
        if res.tells:
            bc = pd.DataFrame([
                {"tx_id": h.tx_id, "category": h.category, "remark": h.remark,
                 "matched": ", ".join(h.matched_terms), "score": h.score,
                 "note": h.note, "source": _cites(h.provenance)}
                for h in res.tells
            ])
            st.dataframe(bc, use_container_width=True, hide_index=True)
            with st.expander("How the match works — show the math"):
                st.markdown(
                    f"**Algorithm:** RapidFuzz — `partial_ratio` for phrases (a short "
                    f"phrase inside a longer remark, threshold **≥ {_PHRASE_THRESHOLD}**) "
                    f"and whole-word `ratio` for entity aliases (threshold "
                    f"**≥ {_ALIAS_THRESHOLD}**), so nicknames and transliterations are "
                    "caught without short tokens matching unrelated substrings."
                )
                st.markdown(
                    "The score is the **best fuzzy-match similarity (0–100) for human "
                    "review — not a risk score.** Each row's `source` cites the exact "
                    "transaction whose remark matched."
                )
        else:
            st.info("No remark tells surfaced across the dataset.")

    # -- RFI --------------------------------------------------------------- #
    with tab_rfi:
        _render_rfi(res.rfi, res.contradictions, res.rfi_decomposition)

    # -- Advisory ---------------------------------------------------------- #
    with tab_advisory:
        st.subheader("Regulatory advisory match")
        st.caption(
            "Scope: US / FinCEN advisories → SAR. "
            "Multi-jurisdiction (EU AMLD/MiCA, UK, FATF) is on the roadmap."
        )
        if res.advisory:
            a = res.advisory
            st.markdown(f"**{a.advisory_id}** — {a.title}")
            _source_caption(a.provenance, prefix="match evidence")
            if a.signals:
                badge = "  ·  ".join(f"`{s}`" for s in a.signals)
                corr = "  ·  **corroborated**" if a.corroborated else ""
                st.markdown(f"Signals that fired: {badge}{corr}")
            st.success(f"SAR key term to cite: **{a.sar_key_term}**  ·  SAR fields: {a.sar_fields}")

            # Signal 1 — keyword / regex over the case text.
            if a.matched_terms:
                terms = ", ".join(f"`{t}`" for t in a.matched_terms)
                st.markdown(f"**Keyword** — matched trigger term(s): {terms}")

            # Signal 2 — semantic red-flag indicators surfaced from the case text.
            if a.semantic_indicators:
                st.markdown("**Semantic** — red-flag indicators surfaced from the case text:")
                for si in a.semantic_indicators:
                    st.caption(f"{si.rf_id} (cosine {si.score:.2f}) — {si.text}  ·  {si.provenance.cite()}")

            # Signal 3 — structured corroborators tying the case to this advisory.
            if a.corroborators:
                st.markdown("**Structured** — corroborators tying the case to this advisory:")
                for c in a.corroborators:
                    st.caption(f"[{c.kind}] {c.detail}  ·  {c.provenance.cite()}")

            with st.expander(f"Red-flag indicators ({len(a.red_flags)})"):
                st.caption(
                    f"Verbatim indicator list from advisory **{a.advisory_id}** — the "
                    "cited source for every flag below. Which indicators this case "
                    "actually evidences is shown above (Semantic / Structured, each "
                    "with its row-level citation)."
                )
                for rf in a.red_flags:
                    st.markdown(f"- {rf}")

            with st.expander("Show the retrieval"):
                cfg = retrieval_config()
                st.markdown(
                    f"- Active embedder this run: `{res.advisory_embedder}`\n"
                    f"- Configured embedder: `{cfg['embedder']}` "
                    f"(deterministic fallback `{cfg['embedder_fallback']}`)\n"
                    f"- Semantic threshold: `{cfg['semantic_threshold']}`  ·  top-k: `{cfg['top_k']}`\n"
                    f"- Corroboration rule: {cfg['corroboration_rule']}\n"
                    f"- Retrieval methodology version: `v{RETRIEVAL_VERSION}`"
                )
                st.caption(
                    "The matcher surfaces and flags advisory relevance for human review — "
                    "it does not determine or file. See docs/advisory-methodology.md."
                )
                st.json(cfg)
        else:
            st.info("No advisory matched (event-triggered on RFI key terms).")

    # -- Decisions (bounded agency + case-graph memory) --------------------- #
    with tab_decisions:
        _render_decisions(res)

    # -- SAR draft --------------------------------------------------------- #
    with tab_sar:
        st.subheader("Grounded, self-critiquing SAR draft")
        if res.sar is None:
            # The sufficiency gate referred the case to a human: no draft was
            # attempted and nothing was fabricated (see the audit trail's
            # human_referral record). Not reachable on the planted scenario.
            st.warning(
                "No draft was attempted: the evidence-sufficiency gate referred "
                "this case to a human investigator (insufficient grounded "
                "evidence for a citable narrative)."
            )
        else:
            st.error(res.sar.disclaimer)
            st.caption(res.sar.filing_note)
            for i, claim in enumerate(res.sar.claims, start=1):
                st.markdown(f"**[{i}] ({claim.element})** {claim.statement}")
                st.caption("source: " + claim.citations())
            ungrounded = res.sar.ungrounded()
            if ungrounded:
                st.error(f"{len(ungrounded)} uncitable claim(s) — grounding contract violated!")
            else:
                st.success(
                    "Every claim carries provenance that resolves to a real evidence "
                    "row — grounding contract satisfied (fail-closed)."
                )

            # -- Critic review (deterministic FinCEN rubric) --------------- #
            crit = res.critique
            history = res.critique_history
            if crit is not None:
                st.markdown("---")
                st.subheader("Critic review (FinCEN rubric)")
                cov_col, bar_col = st.columns([1, 2])
                cov_col.metric("Rubric coverage", f"{crit.coverage:.0%}")
                if crit.meets_bar():
                    bar_col.success("Draft clears the Critic bar — full rubric coverage.")
                else:
                    bar_col.warning(
                        "Below the Critic bar — uncovered element(s) flagged for analyst review."
                    )

                # Which numbered claim(s) satisfy each rubric element — the claim
                # numbers match the [n] list above, so every "yes" is traceable
                # to the cited claims behind it (rubric mapping: FINCEN_RUBRIC).
                elements_for = {e.key: e.claim_elements for e in FINCEN_RUBRIC}
                grade_df = pd.DataFrame([
                    {"element": g.label, "covered": "yes" if g.passed else "no",
                     "required": "yes" if g.required else "no",
                     "satisfied_by_claim": ", ".join(
                         f"[{i}]" for i, c in enumerate(res.sar.claims, start=1)
                         if c.element in elements_for.get(g.key, ())
                     ) or "—"}
                    for g in crit.grades
                ])
                st.dataframe(grade_df, use_container_width=True, hide_index=True)

                if history is not None:
                    if history.revisions:
                        st.caption(
                            f"Revision loop: {history.iterations} bounded pass(es), "
                            f"coverage {history.initial.coverage:.0%} -> {history.final.coverage:.0%}."
                        )
                        for k, addressed in enumerate(history.revisions, start=1):
                            st.caption(f"  pass {k}: added grounded claim(s) for {', '.join(addressed)}")
                    else:
                        st.caption("Revision loop: first draft already cleared the bar (0 passes).")
                    if history.flagged:
                        st.warning(
                            "Human-review fallback — the evidence does not support: "
                            f"{', '.join(history.flagged)}. These are flagged for an analyst, "
                            "never fabricated."
                        )

    # -- Audit trail ------------------------------------------------------- #
    with tab_audit:
        st.subheader("Tamper-evident audit trail")
        st.caption(
            "Every access, tool call, decision, and stamp — hash-chained: each "
            "record's `hash` is the SHA-256 of its own payload **including the "
            "previous record's `hash`** (`prev_hash`; the first record chains from "
            "the all-zero genesis hash). Mutate, drop, or reorder any record and "
            "every hash from that point on stops matching. The chain below shows "
            "the hashes themselves — verify any link by eye: row *n*'s `prev_hash` "
            "equals row *n−1*'s `hash`."
        )
        if res.audit_verified:
            st.success(
                "Hash chain verified — the log is intact and append-only "
                f"(chain tip `{res.audit_records[-1]['hash'][:16]}…`, "
                f"{len(res.audit_records)} records)."
            )
        else:
            st.error("Hash chain FAILED verification — the log was tampered with.")

        # Reviewable, not just provable: the Audit Narrator reads this very chain
        # and renders a plain-language, citation-backed account of what the agent
        # did, in order (Phase 9). Read-only — it writes nothing to the chain.
        _render_audit_narrative(res.audit_records, family="case",
                                subject=f"uid:{res.subject_uid}")

        st.markdown("**Raw hash chain**")
        audit_df = pd.DataFrame([
            {"seq": r["seq"], "timestamp": r["timestamp"], "actor": r["actor"],
             "action": r["action"], "target": r.get("target"), "detail": r.get("detail"),
             "provenance": "; ".join(r["provenance"]) if r.get("provenance") else None,
             "prev_hash": r["prev_hash"], "hash": r["hash"]}
            for r in res.audit_records
        ])
        st.dataframe(audit_df, use_container_width=True, hide_index=True)

        if res.package_path is not None and res.package_path.exists():
            st.markdown("---")
            st.subheader("Decision-ready case package")
            st.caption(
                "Assembled ON the audit trail: the package references each chain "
                "record by (seq, hash), and the chain's `packaged` stamp carries "
                "the package file's SHA-256 — the log covers the package and the "
                "package pins the log. Assembled for human review; nothing is filed."
            )
            st.download_button(
                "Download case_package.json",
                data=res.package_path.read_bytes(),
                file_name=f"case_{res.subject_uid}_package.json",
                mime="application/json",
            )
            st.caption(f"SHA-256: `{res.package_sha256}`")


if __name__ == "__main__":
    main()
