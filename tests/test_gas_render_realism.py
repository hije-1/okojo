"""Gas-funding realism invariants (Branch A — render-level correctness).

A gas top-up is an on-chain, address-level, native-coin (TRX) event. An off-chain
exchange *account* (a ledger entry) cannot pay on-chain gas for a self-hosted
wallet — no protocol mechanism (Tron delegation, ERC-4337 paymasters, Solana
feePayer) lets it. So the graph must render the inference as three cited steps —

    account --(controls, attribution)--> funder wallet
            --(gas top-up TRX, observed)--> funded wallets

— and never as an account-sourced edge to the funded wallets. These three
invariants pin that contract in the DATA and in the RENDER.
"""

from __future__ import annotations

from okojo.network import expand
from okojo.network.render import _ON_CHAIN_RENDER_ETYPES, iter_render_edges


def _gas_subject_uid(conn) -> int:
    """The ultimate controller — the subject whose cluster carries the gas
    tell — derived from roles, never hardcoded."""
    return next(
        a["uid"] for a in conn.all_accounts()
        if a["role_in_ring"] == "ultimate_controller"
    )


# --------------------------------------------------------------------------- #
# (i) No uid is ever a gas funder in the DATA.
# --------------------------------------------------------------------------- #
def test_invariant_i_gas_funder_is_always_an_onchain_address(conn):
    funds = conn.gas_funds()
    assert funds, "expected gas-funding rows in the scenario"
    for gf in funds:
        for col in ("funder_address", "funded_address"):
            ref = str(gf[col])
            assert not ref.startswith("uid:"), (
                f"{col}={ref!r} is a uid — a gas funder/fundee must be an on-chain "
                "address, never an account"
            )
        # the funder resolves to a real on-chain address row
        assert conn.get_address(str(gf["funder_address"])) is not None, (
            f"gas funder {gf['funder_address']!r} is not a known on-chain address"
        )


# --------------------------------------------------------------------------- #
# (ii) No rendered on-chain edge originates at an account node, and the internal
#      gas_control collapse never reaches the render.
# --------------------------------------------------------------------------- #
def test_invariant_ii_no_onchain_edge_from_account_node(conn):
    uid = _gas_subject_uid(conn)
    g = expand(conn, uid, max_hops=7).graph
    rendered = list(iter_render_edges(g))
    hop_nodes = {
        n for n, d in g.nodes(data=True)
        if d.get("addr_label") == "non-custodial-hop"
    }

    # The internal attribution construct is never drawn.
    assert all(etype != "gas_control" for _, _, etype, *_ in rendered), (
        "gas_control (account -> funded hop) must not be rendered"
    )

    # No on-chain edge (a gas top-up) originates at an account node.
    for src, dst, etype, *_ in rendered:
        if etype in _ON_CHAIN_RENDER_ETYPES:
            assert src.startswith("addr:"), (
                f"on-chain edge {etype} originates at non-address node {src!r}"
            )
            assert dst.startswith("addr:"), (
                f"on-chain edge {etype} terminates at non-address node {dst!r}"
            )

    # The account never points at a "non-custodial" hop via an attribution or gas
    # edge: its control of the hop is the INFERENCE the gas-funding reveals, shown
    # through the funder wallet — not pre-drawn. (A uid-leg *transaction* to a hop
    # is a legitimate exchange-ledger record and is allowed.)
    for src, dst, etype, *_ in rendered:
        if src.startswith("acct:") and dst in hop_nodes:
            assert etype not in ("controls", "gas_funding", "gas_control"), (
                f"account {src} points at non-custodial hop {dst} via {etype} — "
                "the account must reach a hop only through the funder wallet"
            )

    # And the three-step chain IS present: the account controls the funder
    # wallet (attribution), which tops up the funded wallets (observed).
    funder_nodes = {s for s, _, e, *_ in rendered if e == "gas_funding"}
    assert funder_nodes, "expected gas_funding (funder -> funded) edges in the render"
    attrib_targets = {
        d for s, d, e, *_ in rendered
        if e == "controls" and s.startswith("acct:") and d in funder_nodes
    }
    assert attrib_targets == funder_nodes, (
        "every gas-funder wallet must have an account -> funder controls edge "
        "(the rendered attribution step)"
    )


# --------------------------------------------------------------------------- #
# (iii) Every gas-funding row is native-coin (TRX) denominated — never USDT.
# --------------------------------------------------------------------------- #
def test_invariant_iii_gas_is_native_coin_never_usdt(conn):
    uid = _gas_subject_uid(conn)
    g = expand(conn, uid, max_hops=7).graph
    gas_edges = [e for e in iter_render_edges(g) if e[2] == "gas_funding"]
    assert gas_edges, "expected gas_funding edges to assert denomination on"
    for src, dst, etype, color, dashes, title in gas_edges:
        if etype == "gas_funding":
            assert "TRX" in title, f"gas edge title omits native coin: {title!r}"
            assert "USDT" not in title.split("TRC-20")[0], (
                f"gas edge denominated as USDT (a token cannot pay its own gas): {title!r}"
            )
