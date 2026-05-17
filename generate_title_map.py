#!/usr/bin/env python3
"""generate_title_map — interactive DAG of title lineage + transaction terms.

Per Jonathan 2026-05-17: legal team needs to SEE the chain visually with hover-
revealed substantive terms. Built on networkx (graph model) + pyvis (interactive
HTML with physics).

Data sources:
  - title_chain (parent→child edges, post-cleanup)
  - title_transfers (where it exists)
  - documents.{lot_number, subdivision_plan, area_sqm, consideration_price,
              grantor_seller, grantee_buyer}  — hover content per edge

Output: /root/landtek/drafts/MWK_Title_Network.html (self-contained, opens in any browser)

Nodes:
  - Each canonical title (OCT T-NNN, T-NNNNN, T-NNN-NNNNNNNNNN)
  - Color-coded: OCT=blue, contested=red, T-4497 chain=orange, CARP=green, others=gray
Edges:
  - Direction: parent → derivative
  - Hover: instrument type, date, lot, area, consideration, grantor, grantee
  - Edge color: red for contested-target, default gray
"""
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2, psycopg2.extras

# Reuse phantom-filter / normalization from build_title_tree
from build_title_tree import is_real_title, NORMALIZATIONS, CARP_TITLES, CONTESTED
from retag_matter_codes import T4497_CHAIN

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
OUT_HTML = Path("/root/landtek/drafts/MWK_Title_Network.html")


def normalize(t):
    if not t: return None
    t = t.strip()
    if t in NORMALIZATIONS:
        return NORMALIZATIONS[t]
    return t if is_real_title(t) else None


def node_color(title):
    """Color by case relevance."""
    if title in CONTESTED:
        return "#e74c3c"  # red — VOID/contested
    if title.startswith("OCT"):
        return "#3498db"  # blue — original certificate
    if title in T4497_CHAIN:
        return "#e67e22"  # orange — T-4497 chain (CV-26-360 theater)
    if title in CARP_TITLES:
        return "#27ae60"  # green — CARP / CV-6839 set
    return "#95a5a6"      # gray — other


def node_label(title):
    """Two-line label: title + matter context."""
    extra = ""
    if title in CONTESTED:
        extra = "\nVOID per CV-26-360"
    elif title in T4497_CHAIN:
        extra = "\n[T-4497 chain]"
    elif title in CARP_TITLES:
        extra = "\n[CV-6839 CARP]"
    return f"{title}{extra}"


def node_title_hover(title):
    """Detail-on-hover for the node itself."""
    parts = [f"<b>{title}</b>"]
    if title in CONTESTED:
        parts.append(f"<i>⚠ {CONTESTED[title]}</i>")
    if title in T4497_CHAIN:
        parts.append("Part of T-4497 chain (CV-26-360)")
    if title in CARP_TITLES:
        parts.append("Part of CV-6839 CARP title set")
    return "<br>".join(parts)


def edge_hover(rec):
    """Build the rich hover-text for an edge from joined data."""
    lines = []
    if rec.get("instrument_type"):
        lines.append(f"<b>{rec['instrument_type']}</b>")
    if rec.get("relationship"):
        lines.append(f"<i>{rec['relationship']}</i>")
    if rec.get("transfer_date"):
        lines.append(f"Date: {rec['transfer_date']}")
    if rec.get("lot_number"):
        lines.append(f"Lot: {rec['lot_number']}")
    if rec.get("subdivision_plan"):
        lines.append(f"Plan: {rec['subdivision_plan']}")
    if rec.get("area_sqm") is not None:
        lines.append(f"Area: {float(rec['area_sqm']):,.0f} sqm")
    if rec.get("consideration_price") is not None:
        cur = rec.get("consideration_currency") or "PHP"
        lines.append(f"Price: {cur} {float(rec['consideration_price']):,.2f}")
    if rec.get("grantor_seller"):
        lines.append(f"From: {rec['grantor_seller']}")
    if rec.get("grantee_buyer"):
        lines.append(f"To: {rec['grantee_buyer']}")
    if rec.get("provenance_level"):
        lines.append(f"<i>provenance: {rec['provenance_level']}</i>")
    if rec.get("source_doc_id"):
        lines.append(f"<i>doc#{rec['source_doc_id']}</i>")
    return "<br>".join(lines) if lines else "(no detail)"


def main():
    import networkx as nx
    from pyvis.network import Network

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    G = nx.DiGraph()

    # 1. Pull title_chain edges (the structural backbone)
    cur.execute("""
        SELECT tc.parent_title, tc.child_title, tc.relationship,
               tc.provenance_level, tc.source_doc_id,
               d.lot_number, d.subdivision_plan, d.area_sqm,
               d.consideration_price, d.consideration_currency,
               d.grantor_seller, d.grantee_buyer,
               d.doc_date_norm AS transfer_date,
               d.classification AS instrument_type
          FROM title_chain tc
          LEFT JOIN documents d ON d.id = tc.source_doc_id
         WHERE tc.case_file = 'MWK-001'
    """)
    chain_edges = cur.fetchall()

    # 2. Pull title_transfers (richer terms when present)
    cur.execute("""
        SELECT tt.parent_title, tt.derivative_title AS child_title,
               'derivative' AS relationship,
               'verified' AS provenance_level,
               tt.transfer_date,
               tt.instrument_type,
               COALESCE(tt.transferor, d.grantor_seller) AS grantor_seller,
               COALESCE(tt.transferee_name, d.grantee_buyer) AS grantee_buyer,
               d.lot_number, d.subdivision_plan, d.area_sqm,
               d.consideration_price, d.consideration_currency,
               COALESCE(tt.cnr_received_doc_id, tt.cancelled_by_doc_id) AS source_doc_id
          FROM title_transfers tt
          LEFT JOIN documents d ON d.id = COALESCE(tt.cnr_received_doc_id, tt.cancelled_by_doc_id)
         WHERE tt.case_file = 'MWK-001'
    """)
    transfer_edges = cur.fetchall()

    # Dedup edges: prefer transfer-row data over title_chain (richer)
    edges = {}
    for e in chain_edges:
        p = normalize(e["parent_title"])
        c = normalize(e["child_title"])
        if not p or not c or p == c: continue
        edges[(p, c)] = e
    for e in transfer_edges:
        p = normalize(e["parent_title"])
        c = normalize(e["child_title"])
        if not p or not c or p == c: continue
        existing = edges.get((p, c))
        # Always prefer transfer-row data if it has more fields populated
        score_existing = sum(1 for k in ("instrument_type","transfer_date","consideration_price",
                                          "grantor_seller","grantee_buyer","lot_number")
                              if existing and existing.get(k))
        score_new = sum(1 for k in ("instrument_type","transfer_date","consideration_price",
                                     "grantor_seller","grantee_buyer","lot_number")
                         if e.get(k))
        if score_new > score_existing:
            edges[(p, c)] = e

    # Add nodes + edges
    for (p, c), e in edges.items():
        if p not in G:
            G.add_node(p, label=node_label(p), title=node_title_hover(p),
                       color=node_color(p))
        if c not in G:
            G.add_node(c, label=node_label(c), title=node_title_hover(c),
                       color=node_color(c))
        edge_color = "#e74c3c" if c in CONTESTED else "#7f8c8d"
        G.add_edge(p, c, title=edge_hover(e), color=edge_color,
                   arrows={"to": {"enabled": True, "scaleFactor": 0.8}})

    print(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Build pyvis Network
    net = Network(height="900px", width="100%", directed=True,
                  bgcolor="#f9f9f9", font_color="#1a1a1a",
                  notebook=False, cdn_resources='in_line')

    # Use hierarchical layout for a clean lineage view
    net.barnes_hut(gravity=-30000, central_gravity=0.3, spring_length=200,
                   spring_strength=0.05, damping=0.4, overlap=0)

    for node, data in G.nodes(data=True):
        net.add_node(node, label=data.get("label", node),
                     title=data.get("title", node),
                     color=data.get("color", "#95a5a6"),
                     size=25 if node in ("OCT T-106", "T-4497", "T-52540") else 18)

    for src, dst, data in G.edges(data=True):
        net.add_edge(src, dst, title=data.get("title", ""),
                     color=data.get("color", "#7f8c8d"),
                     arrows="to", width=1.5)

    # Generate HTML with pyvis (returns string)
    OUT_HTML.parent.mkdir(exist_ok=True)
    html = net.generate_html(notebook=False)

    # Add a small legend at top
    legend = """
    <div style="position:fixed;top:10px;left:10px;background:white;padding:12px;
                border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-family:Arial;
                font-size:12px;z-index:1000;max-width:280px;">
      <b>MWK-001 Title Network</b><br>
      Hover edges for transaction terms.<br><br>
      <span style="display:inline-block;width:12px;height:12px;background:#3498db;border-radius:50%"></span>
        OCT (original certificate)<br>
      <span style="display:inline-block;width:12px;height:12px;background:#e67e22;border-radius:50%"></span>
        T-4497 chain (CV-26-360 theater)<br>
      <span style="display:inline-block;width:12px;height:12px;background:#27ae60;border-radius:50%"></span>
        CV-6839 CARP titles<br>
      <span style="display:inline-block;width:12px;height:12px;background:#e74c3c;border-radius:50%"></span>
        CONTESTED / VOID per our theory<br>
      <span style="display:inline-block;width:12px;height:12px;background:#95a5a6;border-radius:50%"></span>
        Other titles
    </div>
    """
    html = html.replace("<body>", "<body>" + legend, 1)

    OUT_HTML.write_text(html)
    size_kb = OUT_HTML.stat().st_size / 1024
    print(f"✓ Wrote {OUT_HTML} ({size_kb:.0f} KB)")
    print(f"  Open in browser: file://{OUT_HTML}")


if __name__ == "__main__":
    main()
