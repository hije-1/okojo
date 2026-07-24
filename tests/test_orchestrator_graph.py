"""The LangGraph conversion is mechanical: same order, same outputs, no I/O.

Three guarantees pinned here:
1. Graph shape — the node and edge sets are exactly the fixed backbone
   (legibility is a compliance feature; any topology change must show up in
   this test's diff).
2. Byte determinism — two runs with an injected audit clock produce
   byte-identical audit chains.
3. Offline posture — the run path opens no network sockets, and the
   LangChain/LangSmith tracing environment variables are not required to be
   unset for that to hold (the test clears them and blocks sockets outright).
"""

from __future__ import annotations

import socket

from okojo.orchestrator import build_case_graph, run_case

# The full topology: the fixed component backbone plus the five bounded
# decision points and their effect nodes. Slice B replaced the atomic
# network_expander node with the seed/hop/decide/finalize loop and inserted
# the decision nodes -- this pin was updated in the same slice, deliberately:
# any future topology change must show up as a diff here.
_NODES = (
    "case_open",
    "profile_aggregator",
    "network_seed",
    "network_hop",
    "decide_expand",
    "network_finalize",
    "risk_scorer",
    "entity_backbone",
    "remark_miner",
    "advisory_matcher",
    "decide_second_advisory",
    "attach_secondary",
    "rfi_reader",
    "rfi_checker",
    "decide_re_rfi",
    "draft_rfi_followup",
    "decide_sufficiency",
    "sar_drafter",
    "human_referral",
    "decide_sar_bar",
    "case_packager",
    "audit_finalize",
)

_EDGES = {
    ("__start__", "case_open"),
    ("case_open", "profile_aggregator"),
    ("profile_aggregator", "network_seed"),
    ("network_seed", "network_hop"),
    ("network_hop", "decide_expand"),
    # D1: continue the hop loop, or finalize (cap / exhausted frontier)
    ("decide_expand", "network_hop"),
    ("decide_expand", "network_finalize"),
    ("network_finalize", "risk_scorer"),
    ("risk_scorer", "entity_backbone"),
    ("entity_backbone", "remark_miner"),
    ("remark_miner", "advisory_matcher"),
    ("advisory_matcher", "decide_second_advisory"),
    # D2: surface the runner-up advisory, or move on
    ("decide_second_advisory", "attach_secondary"),
    ("decide_second_advisory", "rfi_reader"),
    ("attach_secondary", "rfi_reader"),
    ("rfi_reader", "rfi_checker"),
    ("rfi_checker", "decide_re_rfi"),
    # D3: draft a follow-up RFI for contradicted claims, or move on
    ("decide_re_rfi", "draft_rfi_followup"),
    ("decide_re_rfi", "decide_sufficiency"),
    ("draft_rfi_followup", "decide_sufficiency"),
    # D4: attempt a fail-closed draft, or refer to a human
    ("decide_sufficiency", "sar_drafter"),
    ("decide_sufficiency", "human_referral"),
    # D5: record the disposition; both paths package for human review
    ("sar_drafter", "decide_sar_bar"),
    ("decide_sar_bar", "case_packager"),
    ("human_referral", "case_packager"),
    ("case_packager", "audit_finalize"),
    ("audit_finalize", "__end__"),
}


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"2026-01-01T00:{n['i'] // 60:02d}:{n['i'] % 60:02d}+00:00"

    return clock


def test_graph_shape_is_pinned():
    g = build_case_graph().get_graph()
    assert set(g.nodes) == {"__start__", "__end__", *_NODES}
    assert {(e.source, e.target) for e in g.edges} == _EDGES


def test_two_runs_produce_byte_identical_audit_chains(conn, trust_uid, tmp_path):
    a = run_case(trust_uid, conn=conn, out_dir=tmp_path / "a",
                 render_graph=False, audit_clock=_counter())
    b = run_case(trust_uid, conn=conn, out_dir=tmp_path / "b",
                 render_graph=False, audit_clock=_counter())
    assert a.audit_verified and b.audit_verified
    assert a.audit_log_path.read_bytes() == b.audit_log_path.read_bytes()


def test_run_case_opens_no_network_sockets(conn, trust_uid, tmp_path, monkeypatch):
    for var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_ENDPOINT",
                "LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)

    def _blocked(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("network socket opened during run_case")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    assert res.audit_verified is True
    assert res.sar.claims
