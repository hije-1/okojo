"""Okojo — Streamlit demo (Phase 2).

Pick a synthetic subject and watch one case flow end-to-end: an anomaly-flagged
timeline, the network graph with gas-funding collapse, per-account on-chain
sanctioned-exposure scoring, remark tells, SDN/alias watchlist screening, the
matched FinCEN advisory, a grounded SAR draft, and the tamper-evident audit trail.

Run it:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from okojo.connectors import Connectors
from okojo.network import build_roster
from okojo.orchestrator import run_case
from okojo.orchestrator.pipeline import default_out_dir

st.set_page_config(page_title="Okojo — Crypto-Investigations Co-Pilot", layout="wide")

_SEVERITY_COLOR = {"high": "#dc2626", "medium": "#f59e0b", "low": "#0ea5e9"}
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
[class*="st-key-roster_row_low_"]    { border-left: 4px solid #0ea5e9; }
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


# RFI claim ground-truth label -> (display text, accent colour). Scenario-declared,
# not the output of a live contradiction engine.
_RFI_GT = {
    "false": ("False — contradicted (scenario)", "#dc2626"),
    "partly_true_but_omits_control": ("Partly true — omits control", "#f59e0b"),
    "unverifiable": ("Unverifiable", "#6b7280"),
    "true": ("Consistent with evidence", "#16a34a"),
}


def _render_rfi(rfi) -> None:
    st.subheader("Request for Information (RFI)")
    st.caption(
        "Read-only view of the subject's RFI. Claim assessments are **declared by the "
        "synthetic scenario** (ground truth), not the output of a live analysis — automated "
        "claim-by-claim contradiction testing is the Phase 5 RFI Contradiction-Checker."
    )
    if rfi is None:
        st.info(
            "No RFI on record for this subject. In this scenario the licensed-trust "
            "intermediary (uid 500000003) is the RFI subject."
        )
        return

    st.markdown(f"**{rfi.rfi_id}** · subject uid {rfi.uid}")
    st.markdown("**Investigator question**")
    st.markdown(f"> {rfi.question}")
    st.markdown("**Account-holder response**")
    st.markdown(f"> {rfi.response_text}")

    st.markdown("---")
    st.markdown(f"**Decomposed claims ({len(rfi.claims)})**")
    for c in rfi.claims:
        label, color = _RFI_GT.get(c.ground_truth, (c.ground_truth or "unlabelled", _RISK_GREY))
        st.markdown(
            f"{_chip(f'{c.claim_id} · {label}', color)}<br>{c.text}",
            unsafe_allow_html=True,
        )
        if c.contradicted_by:
            st.caption("Scenario notes this is contradicted by:")
            for note in c.contradicted_by:
                st.markdown(f"- {note}")
        st.markdown("")


def main() -> None:
    st.markdown(
        "<h1 style='font-size:1.6rem;font-weight:700;margin:0 0 0.25rem;'>"
        "Okojo — Agentic Crypto-Investigations Co-Pilot</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Phase 2 · **fully synthetic data** · a human reviews, decides, and files.")

    try:
        conn = get_connectors()
    except FileNotFoundError as exc:
        st.error(f"{exc}")
        st.info("Run `python scripts/generate_scenario.py` to create the synthetic dataset, then reload.")
        return

    accounts = conn.all_accounts()
    label_for = {
        a["uid"]: f"{a['entity_name']}  —  uid {a['uid']}  ({a['role_in_ring']})"
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
        st.header("Case selector")
        st.selectbox(
            "Subject",
            option_uids,
            format_func=lambda uid: label_for.get(uid, f"uid {uid}"),
            key="subject_uid",
        )
        max_hops = st.slider("Network expansion hops", 1, 2, 2)
        st.markdown("---")
        st.markdown(
            "**Reminder:** the agent *proposes, surfaces, drafts, and flags*. "
            "A privileged/internal tag is **flagged for review, never obeyed**."
        )

    subject_uid = st.session_state.subject_uid
    res = run_case(subject_uid, conn=conn, max_hops=max_hops)

    # -- header metrics ---------------------------------------------------- #
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Anomalies", len(res.profile.anomalies))
    c2.metric("Network reached", res.expansion.summary()["accounts_reached"])
    c3.metric("Sanctioned reached", res.expansion.summary()["sanctioned_addresses_reached"])
    c4.metric("Tells", len(res.tells))
    c5.metric("Watchlist hits", len(res.alias_hits))
    c6.metric("Advisory", res.advisory.advisory_id if res.advisory else "—")

    if res.profile.internal_tag:
        st.warning(
            f"Internal 'do-not-block' tag present: {res.profile.internal_tag!r} — "
            "**flagged for review, not obeyed.**"
        )

    names = {a["uid"]: a["entity_name"] for a in accounts}

    (tab_sanctions, tab_timeline, tab_network, tab_tells, tab_rfi,
     tab_advisory, tab_sar, tab_audit) = st.tabs(
        ["Sanctions", "Timeline", "Network", "Tells", "RFI", "Advisory", "SAR draft", "Audit trail"]
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
                 "sdn_id": h.sdn_id, "score": h.score, "program": h.program}
                for h in res.alias_hits
            ])
            st.dataframe(adf, use_container_width=True, hide_index=True)
            st.caption("source: " + "; ".join(
                p.cite() for h in res.alias_hits for p in h.provenance
            ))
        else:
            st.info("No watchlist name hits across the dataset.")

        st.markdown("---")
        st.markdown("#### On-chain sanctioned exposure")
        st.caption(
            "Graded exposure to the synthetic sanctioned set by tainted amount and hop "
            "distance (money-flow path only). Bands: high ≥ 0.60, medium 0.30–0.60. "
            "A full breakdown of how each score is derived is the next slice."
        )
        if res.risk.scores:
            rdf = pd.DataFrame([
                {"uid": str(s.uid), "name": names.get(s.uid, s.uid), "score": s.score,
                 "band": s.band, "hops_to_sanctioned": s.hop_distance,
                 "tainted_usdt": s.tainted_amount_usdt, "reasons": ", ".join(s.reasons),
                 "money_flow": s.exposure_path}
                for s in res.risk.scores
            ])
            st.dataframe(rdf, use_container_width=True, hide_index=True)
            with st.expander("Provenance (per scored account)"):
                for s in res.risk.scores:
                    st.caption(f"uid {s.uid}: " + "; ".join(p.cite() for p in s.provenance))
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
        ev = pd.DataFrame(
            [{"timestamp": e.timestamp, "kind": e.kind, "event": e.description} for e in res.profile.events]
        )
        st.dataframe(ev, use_container_width=True, hide_index=True)

    # -- Network ----------------------------------------------------------- #
    with tab_network:
        st.subheader("Network expansion")
        st.caption(
            "Gold ★ = subject · red ▲ = synthetic-sanctioned endpoint · orange = ring account · "
            "blue = address. Edges: purple = shared device, green = reused KYC, red dashed = gas-funding."
        )
        if res.graph_html_path and Path(res.graph_html_path).exists():
            components.html(Path(res.graph_html_path).read_text(encoding="utf-8"), height=760, scrolling=True)
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
                 "controller_uid": str(l["controller_uid"])}  # uid is an identifier, not a quantity
                for l in gas_links
            ])
            st.dataframe(gdf, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### Connected accounts — triage roster")
        st.caption(
            "Every connected account is a potential case of its own. Sorted by risk "
            "(subject pinned first). **Investigate →** reloads the whole case on that "
            "account. *Case file on record* means a prior run exists on disk — not a "
            "live case-management status."
        )
        risk_by_uid = {s.uid: s for s in res.risk.scores}
        roster = build_roster(conn, res.expansion, default_out_dir(subject_uid).parent)
        _render_roster(roster, risk_by_uid)

    # -- Tells ------------------------------------------------------------- #
    with tab_tells:
        st.subheader("Remark tells")
        if res.tells:
            bc = pd.DataFrame([
                {"tx_id": h.tx_id, "category": h.category, "remark": h.remark,
                 "matched": ", ".join(h.matched_terms), "note": h.note}
                for h in res.tells
            ])
            st.dataframe(bc, use_container_width=True, hide_index=True)
        else:
            st.info("No remark tells.")

    # -- RFI --------------------------------------------------------------- #
    with tab_rfi:
        _render_rfi(res.rfi)

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
            st.markdown(f"Matched term(s): **{', '.join(a.matched_terms)}**")
            st.success(f"SAR key term to cite: **{a.sar_key_term}**  ·  SAR fields: {a.sar_fields}")
            with st.expander(f"Red-flag indicators ({len(a.red_flags)})"):
                for rf in a.red_flags:
                    st.markdown(f"- {rf}")
        else:
            st.info("No advisory matched (event-triggered on RFI key terms).")

    # -- SAR draft --------------------------------------------------------- #
    with tab_sar:
        st.subheader("Grounded SAR draft")
        st.error(res.sar.disclaimer)
        st.caption(res.sar.filing_note)
        for i, claim in enumerate(res.sar.claims, start=1):
            st.markdown(f"**[{i}] ({claim.element})** {claim.statement}")
            st.caption("source: " + claim.citations())
        ungrounded = res.sar.ungrounded()
        if ungrounded:
            st.error(f"{len(ungrounded)} uncitable claim(s) — grounding contract violated!")
        else:
            st.success("Every claim carries provenance — grounding contract satisfied.")

    # -- Audit trail ------------------------------------------------------- #
    with tab_audit:
        st.subheader("Tamper-evident audit trail")
        if res.audit_verified:
            st.success("Hash chain verified — the log is intact and append-only.")
        else:
            st.error("Hash chain FAILED verification — the log was tampered with.")
        audit_df = pd.DataFrame([
            {"seq": r["seq"], "timestamp": r["timestamp"], "actor": r["actor"],
             "action": r["action"], "target": r.get("target"), "detail": r.get("detail")}
            for r in res.audit_records
        ])
        st.dataframe(audit_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
