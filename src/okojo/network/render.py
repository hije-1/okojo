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

# Appended to every generated HTML file: vis.js opens the viewport at an
# arbitrary zoom/center, so fit the view to the full node set once
# stabilization finishes. In the Streamlit embed the file loads inside a
# hidden tab whose canvas has zero width — a fit there is meaningless, and
# neither vis's "resize" event nor a ResizeObserver reliably reports the
# reveal — so a light timer polls the canvas size and re-fits whenever it
# changes (tab reveal, late iframe resize, window resize). The first real
# pointer interaction (drag or wheel zoom) ends the auto-fit for good: after
# that the human owns the viewport and it is never moved under them. Lives in
# the shared render path so the app embed and any standalone open of the HTML
# get the same fitted initial view.
_FIT_SNIPPET = (
    '<script type="text/javascript">\n'
    '(function () {\n'
    '  if (typeof network === "undefined" || network === null) return;\n'
    '  var userTouched = false;\n'
    '  function markTouched(params) {\n'
    '    if (params && (params.event || params.pointer)) { userTouched = true; }\n'
    '  }\n'
    '  network.on("dragStart", markTouched);\n'
    '  network.on("zoom", markTouched);\n'
    '  var lastSize = null;\n'
    '  function tick() {\n'
    '    if (userTouched) return;\n'
    '    var c = network.canvas.frame.canvas;\n'
    '    var size = c.clientWidth + "x" + c.clientHeight;\n'
    '    if (size !== lastSize && c.clientWidth > 0 && c.clientHeight > 0) {\n'
    '      network.fit();\n'
    '    }\n'
    '    lastSize = size;\n'
    '    setTimeout(tick, 400);\n'
    '  }\n'
    '  network.once("stabilizationIterationsDone", function () { lastSize = null; });\n'
    '  tick();\n'
    '})();\n'
    "</script>"
)

_EDGE_STYLE = {
    "transaction": ("#8a8a8a", False),
    "controls": ("#cbd5e1", False),
    "shared_device": ("#7c3aed", False),
    "reused_kyc": ("#16a34a", False),
    "gas_funding": ("#dc2626", True),  # dashed — the controller tell
    "gas_control": ("#b91c1c", True),  # dashed — controller-collapse attribution
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
        # Size and border encode risk so the eye lands on the exposed cluster:
        # bigger node = higher risk; a red border marks the high-risk tier.
        risk = float(data.get("risk", 0.0))
        reasons = data.get("risk_reasons") or []
        if reasons:
            title += f" | risk {risk:.2f}: {', '.join(reasons)}"
        node_kwargs = {"size": 12 + risk * 28}
        if risk >= 0.6:
            node_kwargs["borderWidth"] = 3
            node_kwargs["color"] = {"background": color, "border": "#dc2626"}
        else:
            node_kwargs["color"] = color
        net.add_node(nid, label=str(data.get("label", nid)), shape=shape, title=title, **node_kwargs)

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
    html = html.replace("</body>", _FIT_SNIPPET + "\n</body>", 1)
    out_path.write_text(html, encoding="utf-8")
    return out_path
