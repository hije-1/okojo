"""Static, self-contained pyvis render of a :class:`NetworkExpansion`.

Writes a single standalone HTML file (resources inlined, so it works offline and
embeds cleanly in the Streamlit demo). Nodes and edges are styled by role and
relationship so the money-shot graph reads at a glance: the gold subject, red
synthetic-sanctioned endpoints, and the coloured device / KYC / gas-funding links.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from .expander import NetworkExpansion

_EDGE_STYLE = {
    "transaction": ("#8a8a8a", False),
    "controls": ("#cbd5e1", False),
    "shared_device": ("#7c3aed", False),
    "reused_kyc": ("#16a34a", False),
    "gas_funding": ("#dc2626", True),  # dashed — the controller tell
}


def _node_style(data: dict) -> tuple[str, str, str]:
    """Return (color, shape, title) for a node."""
    if data.get("kind") == "address":
        if data.get("sanctioned"):
            return "#dc2626", "triangle", f"SANCTIONED (synthetic): {data.get('address')}"
        label = data.get("addr_label") or "address"
        return "#0ea5e9", "dot", f"{label}: {data.get('address')}"
    # account
    if data.get("is_subject"):
        return "#f59e0b", "star", f"SUBJECT — {data.get('label')} ({data.get('role')})"
    role = data.get("role")
    if role in (None, "noise"):
        return "#cbd5e1", "dot", f"{data.get('label')} (ordinary)"
    return "#fb923c", "dot", f"{data.get('label')} ({role})"


def render(expansion: NetworkExpansion, out_path: Union[str, Path], height: str = "750px") -> Path:
    from pyvis.network import Network

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    net = Network(height=height, width="100%", directed=True, cdn_resources="in_line", notebook=False)
    # Enable hover tooltips (each node's `title` = its full label/address), zoom
    # controls, and readable label fonts, alongside a barnes-hut layout. The dense
    # graph is hard to read zoomed out, so hover reveals each node on demand while
    # the on-canvas labels stay visible.
    net.set_options(
        '{'
        '"interaction":{"hover":true,"tooltipDelay":120,"navigationButtons":true,"keyboard":false},'
        '"nodes":{"font":{"size":16}},'
        '"edges":{"smooth":false},'
        '"physics":{"barnesHut":{"gravitationalConstant":-8000,"springLength":130,'
        '"springConstant":0.04},"minVelocity":0.75,"stabilization":{"iterations":150}}'
        '}'
    )

    for nid, data in expansion.graph.nodes(data=True):
        color, shape, title = _node_style(data)
        net.add_node(nid, label=str(data.get("label", nid)), color=color, shape=shape, title=title)

    for u, v, data in expansion.graph.edges(data=True):
        etype = data.get("etype", "transaction")
        color, dashes = _EDGE_STYLE.get(etype, ("#8a8a8a", False))
        title = etype
        if etype == "transaction" and data.get("amount") is not None:
            title = f"transaction: {data['amount']:,.0f} USDT"
            if data.get("remark"):
                title += f' — "{data["remark"]}"'
        net.add_edge(u, v, color=color, dashes=dashes, title=title)

    # NB: pyvis's own write_html opens the file with the platform locale codec
    # (cp1252 on Windows), which crashes on accented Faker names. Generate the
    # HTML and write it ourselves as UTF-8.
    html = net.generate_html(notebook=False)
    out_path.write_text(html, encoding="utf-8")
    return out_path
