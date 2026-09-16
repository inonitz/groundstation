#!/usr/bin/env python3
"""Graphviz DOT -> native draw.io file, keeping graphviz's layout (positions, sizes, fills, edge colours).
Boxes, diamonds, ellipses, notes and clusters become editable shapes; edges become orthogonal connectors.
    python3 dot2drawio.py <file.dot> [more.dot ...]     -> writes <file>.drawio next to each source
Slide recipe (2026-09-09): render PNG with `dot -Tpng`, SVG with `dot -Tsvg:cairo` (glyphs become paths, so no
font substitution can break the labels; verify with grep -c '<text' = 0), and this file for hand edits in draw.io."""
import json, subprocess, html, sys, os
SHAPE = {"box": "rounded=1;whiteSpace=wrap;html=1;", "diamond": "rhombus;whiteSpace=wrap;html=1;",
         "ellipse": "ellipse;whiteSpace=wrap;html=1;", "note": "shape=note;whiteSpace=wrap;html=1;size=14;"}
def label(s): return html.escape(s.replace("\\l", "<br>").replace("\\n", "<br>").replace("\n", "<br>"), quote=True)
def build(dot_path, scale=1.35):
    j = json.loads(subprocess.run(["dot", "-Tjson0", dot_path], capture_output=True, text=True, check=True).stdout)
    H = float(j["bb"].split(",")[3]); S = scale
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']; nid = [2]; gv2id = {}
    def add(text, x, y, w, h, style):
        i = nid[0]; nid[0] += 1
        cells.append(f'<mxCell id="{i}" value="{text}" style="{style}" vertex="1" parent="1"><mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>')
        return i
    for o in j.get("objects", []):                      # clusters first, as background containers
        if o.get("name", "").startswith("cluster") and "bb" in o:
            x1, y1, x2, y2 = map(float, o["bb"].split(","))
            add(label(o.get("label", "")), x1 * S, (H - y2) * S, (x2 - x1) * S, (y2 - y1) * S,
                f"rounded=1;whiteSpace=wrap;html=1;fillColor={o.get('bgcolor', '#f8fafc')};strokeColor={o.get('color', '#94a3b8')};verticalAlign=top;fontStyle=1;fontSize=13;fontFamily=Helvetica;")
    for o in j.get("objects", []):
        if o.get("name", "").startswith("cluster") or "pos" not in o: continue
        x, y = map(float, o["pos"].split(",")); w = float(o["width"]) * 72 * S; h = float(o["height"]) * 72 * S
        st = SHAPE.get(o.get("shape", "box"), SHAPE["box"]) + f"fillColor={o.get('fillcolor', '#ffffff')};strokeColor={o.get('color', '#94a3b8')};fontColor={o.get('fontcolor', '#0f172a')};fontSize={o.get('fontsize', '11')};fontFamily=Helvetica;align=center;"
        if "\\l" in o.get("label", ""): st += "align=left;spacingLeft=6;"
        gv2id[o["_gvid"]] = add(label(o.get("label", o["name"])), x * S - w / 2, (H - y) * S - h / 2, w, h, st)
    for e in j.get("edges", []):
        if e["tail"] not in gv2id or e["head"] not in gv2id: continue
        i = nid[0]; nid[0] += 1
        dashed = ";dashed=1" if e.get("style") in ("dashed", "dotted") else ""
        both = ";startArrow=classic;startFill=1" if e.get("dir") == "both" else ""
        cells.append(f'<mxCell id="{i}" value="{label(e.get("label", ""))}" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor={e.get("color", "#64748b")};strokeWidth={e.get("penwidth", "1.1")};fontSize=9;fontFamily=Helvetica;fontColor={e.get("fontcolor", "#475569")}{dashed}{both}" edge="1" parent="1" source="{gv2id[e["tail"]]}" target="{gv2id[e["head"]]}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    name = os.path.splitext(os.path.basename(dot_path))[0]
    xml = f'<mxfile host="app.diagrams.net"><diagram name="{name}" id="{name}"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="900" math="0" shadow="0"><root>' + "".join(cells) + '</root></mxGraphModel></diagram></mxfile>'
    import xml.dom.minidom as m; m.parseString(xml)
    out = os.path.splitext(dot_path)[0] + ".drawio"; open(out, "w", encoding="utf-8").write(xml); return out, len(cells) - 2
if __name__ == "__main__":
    for p in sys.argv[1:]:
        out, n = build(p); print(f"{out}: {n} cells")
