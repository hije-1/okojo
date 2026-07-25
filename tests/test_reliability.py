"""Phase 7 reliability harness — the Build-Plan tail as executable properties.

Three prose claims become mechanical assertions over EVERY subject (not just the
kingpin happy path), plus the degenerate cases and pinned past failure modes:

P1  — grounding holds: every SAR claim is grounded AND resolves to a real
      evidence row, via full ``run_case`` (so the advisory / RFI / contradiction
      claim families are exercised, unlike the drafter-only loop tests).
P1b — subject-closure PROPERTY (asserted since the grounding-completeness
      slice): (1) no claim cites a row outside the subject's network closure —
      with one documented, policy-backed exception: an advisory-element claim
      may cite dataset-level corroboration context (e.g. the watchlist hit
      that corroborated the match, per versioned retrieval policy) IFF the
      claim text itself attributes it; and (2) every claim citing a network
      member's rows names that member in its text. Both started as reported
      diagnostics (13 and 39); the fixes were their own slice (CRITIC v1.1.0
      tell-scope gate + drafter-owned attribution), and the harness now
      asserts both at zero.
P2  — the graph always renders: ``render()`` asserted DIRECTLY (unguarded), so
      a real render regression still fails the suite; the orchestrator's guard
      is exercised separately by fault injection (case completes, degradation
      surfaced + audited, never silently swallowed).
P3  — every loop terminates within its declared bound (Critic cap, hop cap —
      including at the real cap of 7 where the frontier-exhausted stop is
      reachable — and the LangGraph recursion limit).
P3b — non-convergence is SAFE: a subject whose draft never clears the bar gets
      a flagged human fallback, never a fabricated claim. ("Loops always
      converge" is false for most subjects by design; this is the honest form.)

The subject set is DERIVED, never hardcoded: the 12 roster subjects come from
``ground_truth["network_member_uids"]``; the isolated (zero-edge) subjects are
computed as the roster's complement filtered to nodes==1/edges==0, so a
generator change can never silently shrink what this harness tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import networkx as nx
import pytest

from okojo.agency import decide_re_rfi
from okojo.audit import AuditLog
from okojo.casegraph import CaseGraphStore
from okojo.connectors import Connectors, Record
from okojo.entity import build_backbone
from okojo.network import NetworkExpansion, clamp_hops, expand, render
from okojo.orchestrator.graph import build_case_graph
from okojo.orchestrator.pipeline import run_case
from okojo.provenance import Provenance
from okojo.remarks import mine_remarks
from okojo.rfi import check_contradictions, decompose
from okojo.sar.loop import MAX_REVISION_ITERATIONS
from okojo.sar.validate import validate_grounding

# ---------------------------------------------------------------------------
# The derived subject set + one shared all-subjects run (module-scoped: the
# harness runs every subject through the full pipeline exactly once).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rconn(data_dir):
    c = Connectors(data_dir=data_dir)
    yield c
    c.close()


@pytest.fixture(scope="module")
def roster_uids(rconn, data_dir) -> list[int]:
    gt = json.loads((data_dir / "ground_truth.json").read_text())
    uids = sorted(gt["network_member_uids"])
    assert len(uids) == 12, "roster drifted — re-derive the harness subject set"
    return uids


@pytest.fixture(scope="module")
def isolated_uids(rconn, roster_uids) -> list[int]:
    """Zero-network subjects, DERIVED as the roster's complement (never magic
    uids): every non-roster account whose expansion is a single node with no
    edges. These are the real degenerate no-network cases."""
    out = []
    for a in rconn.all_accounts():
        uid = int(a["uid"])
        if uid in roster_uids:
            continue
        g = expand(rconn, uid, max_hops=2).graph
        if g.number_of_nodes() == 1 and g.number_of_edges() == 0:
            out.append(uid)
    assert len(out) >= 2, "expected at least two isolated accounts in the scenario"
    return sorted(out)


@pytest.fixture(scope="module")
def subjects(roster_uids, isolated_uids) -> list[int]:
    return roster_uids + isolated_uids


@pytest.fixture(scope="module")
def all_results(rconn, subjects, tmp_path_factory) -> dict:
    """Full ``run_case`` for every subject, once. render_graph=False here;
    P2 exercises the raw ``render()`` directly on these expansions."""
    base = tmp_path_factory.mktemp("reliability")
    return {
        uid: run_case(uid, conn=rconn, out_dir=base / f"c{uid}", render_graph=False)
        for uid in subjects
    }


# ---------------------------------------------------------------------------
# P1 — grounding holds for every subject, through the FULL pipeline.
# ---------------------------------------------------------------------------


def test_p1_grounding_holds_for_every_subject(rconn, all_results):
    for uid, res in all_results.items():
        assert res.sar is not None, f"uid {uid}: no SAR (unexpected human referral)"
        report = validate_grounding(rconn, res.sar)
        assert report.fully_grounded, f"uid {uid}: ungrounded claim(s)"
        assert report.fully_resolved, (
            f"uid {uid}: unresolvable citation(s): "
            + "; ".join(p.cite() for _, ps in report.unresolved for p in ps)
        )
        assert res.audit_verified, f"uid {uid}: audit chain failed verification"


# ---------------------------------------------------------------------------
# P1b — subject-closure diagnostic (two numbers; reported, not asserted).
# ---------------------------------------------------------------------------


def _owner_maps(conn: Connectors) -> dict:
    """Row -> owning uid(s) lookup tables, built once from the evidence stores."""
    addr_owner = {}
    for a in conn.all_addresses():
        cu = a["controller_uid"]
        addr_owner[a["address"]] = int(cu) if cu is not None else None
    tx_refs = {t["tx_id"]: (t["from_ref"], t["to_ref"]) for t in conn.all_transactions()}
    kyc_uids: dict[str, set[int]] = {}
    for a in conn.all_accounts():
        if a["kyc_doc_id"]:
            kyc_uids.setdefault(a["kyc_doc_id"], set()).add(int(a["uid"]))
    rfi_uid = {r["rfi_id"]: int(r["uid"]) for r in conn.all_rfis()}
    rfi_uid.update({r["rfi_id"]: int(r["uid"]) for r in conn.all_prior_rfis()})
    reg_uids = {
        r["registry_id"]: {int(r["company_uid"]), int(r["officer_uid"])}
        for r in conn.all_registry()
    }
    names = {int(a["uid"]): str(a["entity_name"]) for a in conn.all_accounts()}
    return {
        "addr_owner": addr_owner, "tx_refs": tx_refs, "kyc_uids": kyc_uids,
        "rfi_uid": rfi_uid, "reg_uids": reg_uids, "names": names,
    }


def _ref_owner(ref: str, maps: dict) -> set[int]:
    if str(ref).startswith("uid:"):
        return {int(str(ref)[4:])}
    owner = maps["addr_owner"].get(ref)
    return {owner} if owner is not None else set()


def _pointer_owners(p: Provenance, maps: dict) -> tuple[set[int], bool]:
    """(owning uids, is_reference_material) for one provenance pointer."""
    src, key = p.source, p.row_key
    if src == "sdn_list":
        return set(), True
    if src == "accounts":
        return {int(key.split(":")[1])}, False
    if src == "ip_logs":
        return {int(key.split(":")[1].split("@")[0])}, False
    if src == "devices":
        return {int(key.rsplit(":", 1)[1])}, False
    if src == "kyc_docs":
        return set(maps["kyc_uids"].get(key, set())), False
    if src == "addresses":
        owner = maps["addr_owner"].get(key)
        return ({owner} if owner is not None else set()), False
    if src == "transactions":
        refs = maps["tx_refs"].get(key, ())
        owners: set[int] = set()
        for r in refs:
            owners |= _ref_owner(r, maps)
        return owners, False
    if src == "gas_funding":
        owners = set()
        for part in key.split("->"):
            owner = maps["addr_owner"].get(part)
            if owner is not None:
                owners.add(owner)
        return owners, False
    if src in ("rfi", "rfi_prior"):
        uid = maps["rfi_uid"].get(key)
        return ({uid} if uid is not None else set()), False
    if src == "registry":
        return set(maps["reg_uids"].get(key, set())), False
    return set(), True  # unknown source -> treat as reference material


def _statement_attributes(statement: str, owners: set[int], names: dict) -> bool:
    """Does the claim's own text attribute the row to its owner (uid or a
    distinctive name token)? Mechanical proxy for 'the reader can tell whose
    evidence this is'."""
    low = statement.lower()
    for uid in owners:
        if str(uid) in statement:
            return True
        for tok in names.get(uid, "").lower().split():
            if len(tok) >= 4 and tok in low:
                return True
    return False


@pytest.fixture(scope="module")
def closure_diagnostic(rconn, all_results) -> dict:
    maps = _owner_maps(rconn)
    per_subject = {}
    for uid, res in all_results.items():
        net_uids = {
            int(n.split(":")[1])
            for n in res.expansion.graph.nodes
            if str(n).startswith("acct:")
        }
        net_addrs = {
            str(n).split(":", 1)[1]
            for n in res.expansion.graph.nodes
            if str(n).startswith("addr:")
        }
        misattributed, unattributed = [], []
        for claim in res.sar.claims:
            outside = network_ptrs = False
            outside_owners: set[int] = set()
            net_owners: set[int] = set()
            for p in claim.provenance:
                owners, is_ref = _pointer_owners(p, maps)
                if is_ref:
                    continue
                if uid in owners:
                    continue  # the subject's own row
                in_net = bool(owners & net_uids)
                if not in_net and p.source == "addresses" and p.row_key in net_addrs:
                    in_net = True
                if not in_net and p.source == "transactions":
                    refs = maps["tx_refs"].get(p.row_key, ())
                    in_net = any(r in net_addrs or r == f"uid:{uid}" for r in refs)
                if in_net:
                    network_ptrs = True
                    net_owners |= owners - {uid}
                else:
                    outside = True
                    outside_owners |= owners
            # Policy-backed exception (published in the sar-critic methodology,
            # drafting section): an ADVISORY claim may cite dataset-level
            # corroboration context outside the subject's network — the match's
            # real basis under versioned retrieval policy — IFF the claim text
            # itself attributes it. Unattributed, or on any other element, it
            # counts as misattribution.
            if outside and claim.element == "advisory" and outside_owners and \
                    _statement_attributes(claim.statement, outside_owners, maps["names"]):
                outside = False
            if outside:
                misattributed.append(claim)
            elif network_ptrs and net_owners and not _statement_attributes(
                claim.statement, net_owners, maps["names"]
            ):
                unattributed.append(claim)
        per_subject[uid] = {
            "claims": len(res.sar.claims),
            "misattributed": misattributed,
            "unattributed": unattributed,
        }
    return per_subject


def test_p1b_subject_closure_holds_for_every_subject(closure_diagnostic, capsys):
    """ASSERTED since the grounding-completeness slice: no claim cites a row
    outside the subject's closure (advisory corroboration context excepted
    only when the claim text attributes it), and every claim citing a network
    member's rows names that member. Both counts were real defects when this
    harness first measured them (13 and 39); they are pinned at zero now."""
    total_mis = sum(len(d["misattributed"]) for d in closure_diagnostic.values())
    total_unattr = sum(len(d["unattributed"]) for d in closure_diagnostic.values())
    with capsys.disabled():
        print("\nSubject-closure property (P1b - asserted):")
        for uid, d in sorted(closure_diagnostic.items()):
            flags = []
            if d["misattributed"]:
                flags.append(f"OUTSIDE-CLOSURE={len(d['misattributed'])}")
            if d["unattributed"]:
                flags.append(f"network-unattributed={len(d['unattributed'])}")
            print(f"  uid {uid}: claims={d['claims']:2d}  {'  '.join(flags) or 'clean'}")
        print(f"  claims citing rows OUTSIDE subject+network (misattribution): {total_mis}")
        print(f"  claims citing network rows WITHOUT attribution (wording):    {total_unattr}")
    assert len(closure_diagnostic) >= 14
    for uid, d in sorted(closure_diagnostic.items()):
        assert not d["misattributed"], (
            f"uid {uid}: claim(s) cite rows outside the subject's closure: "
            + "; ".join(c.statement[:80] for c in d["misattributed"])
        )
        assert not d["unattributed"], (
            f"uid {uid}: claim(s) cite network rows without attribution: "
            + "; ".join(c.statement[:80] for c in d["unattributed"])
        )


# ---------------------------------------------------------------------------
# P2 — the graph always renders (unguarded render(), content-checked).
# ---------------------------------------------------------------------------


def test_p2_render_directly_for_every_subject(all_results, tmp_path):
    """The raw render() — NOT the orchestrator guard — so a genuine render
    regression fails the suite loudly. Content-checked: every graph node id
    must appear in the emitted HTML, not just '<html' somewhere."""
    for uid, res in all_results.items():
        out = render(res.expansion, tmp_path / f"net_{uid}.html")
        text = out.read_text(encoding="utf-8")
        assert out.exists() and len(text) > 0, f"uid {uid}: empty render"
        assert "<html" in text.lower(), f"uid {uid}: not an HTML document"
        assert "nodes = new vis.DataSet(" in text, f"uid {uid}: no vis node payload"
        for nid in res.expansion.graph.nodes:
            assert f'"id": "{nid}"' in text, f"uid {uid}: node {nid} missing from HTML"


def test_p2_zero_node_graph_renders(tmp_path):
    """A truly empty graph (unreachable via run_case, which always seeds the
    subject node) still renders a valid document rather than raising."""
    empty = NetworkExpansion(graph=nx.MultiDiGraph(), subject_uid=0, max_hops=1)
    out = render(empty, tmp_path / "empty.html")
    text = out.read_text(encoding="utf-8")
    assert "<html" in text.lower() and "nodes = new vis.DataSet([]);" in text


def test_p2_render_handles_non_ascii_labels(tmp_path):
    """Pinned past failure: pyvis's own write_html uses the platform codec
    (cp1252 on Windows) and crashed on accented names. The generator currently
    emits ASCII-only names, so this pin uses a synthetic accented label."""
    g = nx.MultiDiGraph()
    g.add_node("acct:1", kind="account", label="Café Ştefan Ürün",
               role="shell_trading", is_subject=True)
    out = render(NetworkExpansion(graph=g, subject_uid=1, max_hops=1),
                 tmp_path / "accented.html")
    text = out.read_text(encoding="utf-8")
    # pyvis may embed the label raw or JSON-escaped (\uXXXX) — both are
    # faithful; the pinned failure was the cp1252 crash, not the encoding form.
    label = "Café Ştefan Ürün"
    escaped = json.dumps(label)[1:-1]
    assert label in text or escaped in text


def test_p2_render_failure_degrades_never_aborts(rconn, roster_uids, tmp_path):
    """Fault injection on the orchestrator guard: a render failure must not
    abort the case, must surface the degradation, and must stamp the failure
    into the hash chain — while a successful run carries NO failure record."""
    uid = roster_uids[0]
    import okojo.orchestrator.graph as og

    with mock.patch.object(og, "render", side_effect=RuntimeError("injected render failure")):
        res = run_case(uid, conn=rconn, out_dir=tmp_path / "fail", render_graph=True)
    assert res.sar is not None and res.package_sha256 is not None  # case completed
    assert res.graph_html_path is None
    assert res.render_error and "injected render failure" in res.render_error
    fails = [r for r in res.audit_records if r["action"] == "graph_render_failed"]
    assert len(fails) == 1 and "flagged for review" in fails[0]["detail"]
    assert res.audit_verified  # the chain still verifies end-to-end

    # Success path: graph_rendered present, failure record absent, no error.
    ok = run_case(uid, conn=rconn, out_dir=tmp_path / "ok", render_graph=True)
    actions = [r["action"] for r in ok.audit_records]
    assert "graph_rendered" in actions and "graph_render_failed" not in actions
    assert ok.render_error is None and ok.graph_html_path.exists()


# ---------------------------------------------------------------------------
# P3 — every loop terminates within its declared bound.
# ---------------------------------------------------------------------------


def test_p3_critic_and_hop_loops_bounded_for_every_subject(all_results):
    for uid, res in all_results.items():
        assert res.critique_history.iterations <= MAX_REVISION_ITERATIONS, (
            f"uid {uid}: Critic loop exceeded its cap"
        )
        hop_decisions = [d for d in res.decisions if d.decision_id == "expand_hop"]
        cap = clamp_hops(2)
        assert len(hop_decisions) <= cap, f"uid {uid}: more hop decisions than the cap"
        assert hop_decisions[-1].outcome in ("stop_cap", "stop_frontier_exhausted"), (
            f"uid {uid}: hop loop ended on a non-terminal outcome"
        )


def test_p3_hop_loop_terminates_at_the_real_cap(rconn, trust_uid, tmp_path):
    """max_hops=99 clamps to 7 — the walk must stop on frontier exhaustion
    well inside the cap (this is the only path that exercises the
    stop_frontier_exhausted branch at the true limit)."""
    res = run_case(trust_uid, conn=rconn, out_dir=tmp_path, max_hops=99,
                   render_graph=False)
    hop_decisions = [d for d in res.decisions if d.decision_id == "expand_hop"]
    assert 0 < len(hop_decisions) <= clamp_hops(99) == 7
    assert hop_decisions[-1].outcome == "stop_frontier_exhausted"


def test_p3_superstep_count_stays_below_recursion_limit(rconn, trust_uid, tmp_path, capsys):
    """The LangGraph recursion_limit=100 (pipeline.py) had zero coverage. The
    worst case (max hop cap) must complete with wide headroom — streamed
    node-by-node so the superstep count is measured, not assumed."""
    audit = AuditLog(tmp_path / "audit_log.jsonl")
    initial = {
        "subject_uid": trust_uid, "max_hops": 99, "render_graph": False,
        "out_dir": tmp_path, "conn": rconn, "audit": audit,
        "case_store": CaseGraphStore(tmp_path / "case_graph.sqlite"),
    }
    supersteps = sum(
        1 for _ in build_case_graph().stream(
            initial, config={"recursion_limit": 100}, stream_mode="updates",
        )
    )
    with capsys.disabled():
        print(f"\nLangGraph supersteps at hop cap 7: {supersteps} (recursion_limit=100)")
    assert supersteps < 60  # generous margin under the 100 limit


def test_p3b_nonconvergence_yields_flagged_fallback_never_fabrication(rconn, all_results):
    """The honest form of 'loops always converge': most subjects do NOT clear
    the bar, by design — every one of them must carry the flagged human
    fallback, and the grounding contract must still hold on the final draft."""
    nonconverged = {
        uid: res for uid, res in all_results.items()
        if not res.critique_history.converged
    }
    assert nonconverged, "expected non-converging subjects in this scenario"
    for uid, res in nonconverged.items():
        assert res.critique_history.flagged, f"uid {uid}: no flagged elements"
        assert "CRITIC NOTE" in res.sar.filing_note, f"uid {uid}: fallback note missing"
        assert "not fabricated" in res.sar.filing_note
        report = validate_grounding(rconn, res.sar)
        assert report.fully_grounded and report.fully_resolved, (
            f"uid {uid}: non-converged draft broke grounding"
        )


# ---------------------------------------------------------------------------
# Degenerate inputs the scenario does not contain (synthesized at the harness
# level — the generator is the answer key and is never touched).
# ---------------------------------------------------------------------------


def test_degenerate_rfi_with_zero_contradictions(rconn, trust_uid):
    """An RFI whose claims all survive probing must yield no_contradictions —
    qualified/unverifiable verdicts alone never trigger a re-RFI."""
    backbone = build_backbone(rconn)
    table = check_contradictions(
        rconn, trust_uid, backbone, decomposition=decompose(rconn, trust_uid),
    )
    table.adjudications = [a for a in table.adjudications if not a.is_contradiction]
    assert decide_re_rfi(table).outcome == "no_contradictions"


class _RemarkInjector:
    """Connectors wrapper that appends synthetic remark rows the SQL-level
    filter (remark <> '') cannot produce — the whitespace-only degenerate."""

    def __init__(self, base: Connectors, remarks: list[str]):
        self._base = base
        self._extra = [
            Record(
                {"tx_id": f"SIMTX-DEGEN-{i:03d}", "remark": r},
                Provenance(source="transactions", row_key=f"SIMTX-DEGEN-{i:03d}"),
            )
            for i, r in enumerate(remarks)
        ]

    def remarks(self):
        return self._base.remarks() + self._extra

    def __getattr__(self, name):
        return getattr(self._base, name)


def test_degenerate_whitespace_remark_produces_no_tell(rconn):
    """Stated expected behaviour (not merely 'does not crash'): an empty or
    whitespace-only remark yields NO tell — a SAR sentence quoting a blank
    remark would itself be a defect. Real remarks must keep matching."""
    backbone = build_backbone(rconn)
    wrapped = _RemarkInjector(rconn, ["", "   ", "\t \n"])
    tells = mine_remarks(wrapped, backbone=backbone)
    degen = [t for t in tells if t.tx_id.startswith("SIMTX-DEGEN-")]
    assert degen == [], f"whitespace remark produced tell(s): {degen}"
    assert tells, "real remarks stopped matching — miner regression"


# ---------------------------------------------------------------------------
# Pinned past failure modes (previously unguarded).
# ---------------------------------------------------------------------------


def test_pin_hop_stats_stays_out_of_expansion_summary(all_results):
    """Audit byte-identity depends on hop_stats never entering summary():
    stepwise and fixed-cap walks may record different no-op tails."""
    res = next(iter(all_results.values()))
    assert "hop_stats" not in res.expansion.summary()


def test_pin_unknown_uid_fails_loudly(rconn, tmp_path):
    with pytest.raises(ValueError, match="No account with uid"):
        run_case(999999999, conn=rconn, out_dir=tmp_path, render_graph=False)


# ---------------------------------------------------------------------------
# The reliability scorecard (house style: printed under -s).
# ---------------------------------------------------------------------------


def test_reliability_scorecard(rconn, all_results, roster_uids, isolated_uids,
                               closure_diagnostic, capsys):
    p1_ok = all(
        validate_grounding(rconn, r.sar).fully_resolved for r in all_results.values()
    )
    converged = sum(1 for r in all_results.values() if r.critique_history.converged)
    fallbacks = sum(
        1 for r in all_results.values()
        if not r.critique_history.converged and "CRITIC NOTE" in r.sar.filing_note
    )
    total_mis = sum(len(d["misattributed"]) for d in closure_diagnostic.values())
    total_unattr = sum(len(d["unattributed"]) for d in closure_diagnostic.values())
    with capsys.disabled():
        print("\nReliability harness scorecard (full pipeline, all subjects):")
        print(f"  subjects: {len(all_results)} = {len(roster_uids)} roster "
              f"+ {len(isolated_uids)} isolated (derived, not hardcoded)")
        print(f"  P1  grounding+resolution hold everywhere:      {p1_ok}")
        print(f"  P1b subject-closure holds (asserted):          "
              f"outside-closure={total_mis} network-unattributed={total_unattr}")
        print(f"  P2  render content-verified per subject:       True (see test_p2_*)")
        print(f"  P3  loops bounded (critic<= {MAX_REVISION_ITERATIONS}, hops<=cap, "
              f"supersteps<100): True")
        print(f"  P3b non-convergence -> flagged fallback:       "
              f"{fallbacks}/{len(all_results) - converged} non-converging subjects")
    assert p1_ok
    assert fallbacks == len(all_results) - converged
