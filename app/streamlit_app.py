"""Okojo — Streamlit demo (Phase 5).

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from okojo.advisory import RETRIEVAL_VERSION, retrieval_config
from okojo.connectors import Connectors
from okojo.network import build_roster
from okojo.orchestrator import run_case
from okojo.orchestrator.pipeline import default_out_dir
from okojo.remarks import SCREEN_THRESHOLD
from okojo.scorer import SCORING_VERSION, scoring_config

# Brand logo lives at the repo root; resolve off it so the path holds regardless
# of the working directory the app is launched from.
_LOGO_PATH = str(Path(__file__).resolve().parents[1] / "okojo-logo.png")

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

        src = aligned.get(adj.claim_id)
        if src is not None:
            st.caption(
                f"Decomposed from the response (alignment {src.alignment_score:.0f}): "
                f"“{src.source_sentence}”"
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


def main() -> None:
    st.markdown(
        "<h1 style='font-size:1.6rem;font-weight:700;margin:0 0 0.25rem;'>"
        "Okojo — Agentic Crypto-Investigations Co-Pilot</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Phase 5 · **fully synthetic data** · a human reviews, decides, and files.")

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
        # Centered logo at ~5/12 of the sidebar width (middle = 10/24): side
        # spacers center the middle column that carries the image.
        _, _logo_col, _ = st.columns([7, 10, 7])
        _logo_col.image(_LOGO_PATH, use_container_width=True)
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
                        f"watchlist alias: {alias_html}</div>",
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
                 "money_flow": s.exposure_path}
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

                grade_df = pd.DataFrame([
                    {"element": g.label, "covered": "yes" if g.passed else "no",
                     "required": "yes" if g.required else "no"}
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
