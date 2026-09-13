"""src.dot (dot engine, clusters) -> flat layout without clusters (dot honours flat ordering there)
-> deliverable .dot: same clusters, layout=neato, every node pinned (pos=x,y!), clusters spaced apart."""
import subprocess,re,sys
src_p,out_p,gap=sys.argv[1],sys.argv[2],float(sys.argv[3])
src=open(src_p).read()
flat="\n".join(l for l in src.splitlines() if not (l.strip().startswith("subgraph cluster") or l.startswith("    label=") or l=="  }"))
plain=subprocess.run(["dot","-Tplain","/dev/stdin"],input=flat,capture_output=True,text=True).stdout
pos={t[1]:(float(t[2])*72,float(t[3])*72) for t in (l.split() for l in plain.splitlines()) if t and t[0]=="node"}
wid={t[1]:float(t[4])*72 for t in (l.split() for l in plain.splitlines()) if t and t[0]=="node"}
# hand nudges (points): the RC sits centred under the vtx-ctl channel so its top face is reachable; the aircraft to its left
if {"vtx","ctl","rc","ac"} <= set(pos) and {"rc","ac"} <= set(wid):   # harden2-only nudge; auto-skips on other graphs
    rx=(pos["vtx"][0]+pos["ctl"][0])/2; pos["rc"]=(rx,pos["rc"][1])
    pos["ac"]=(rx-(wid["rc"]+wid["ac"])/2-0.9*72,pos["ac"][1])
for n,dx in (eval(sys.argv[4]) if len(sys.argv)>4 else {}).items(): pos[n]=(pos[n][0]+dx,pos[n][1])   # extra per-node x nudges (points)
# cluster membership by textual position in src
order=[]; cur=None
for l in src.splitlines():
    m=re.match(r'\s*subgraph (cluster_\w+)',l)
    if m: cur=m.group(1); order.append(cur); continue
    m=re.match(r'\s+(\w+)\s+\[fillcolor',l)
    if m and cur: pos.setdefault(m.group(1),None); pos[m.group(1)]=(pos[m.group(1)][0],pos[m.group(1)][1]-gap*order.index(cur))
out=src.replace("graph [rankdir=TB, splines=ortho, compound=true,","graph [layout=neato, inputscale=72, splines=ortho, compound=true,")
out=out.replace("// Invisible edges only pin the column grid; they carry no meaning.",
 "// Invisible edges only pin the column grid; they carry no meaning.\n// Positions are PINNED (pos=...!): the grid comes from a dot pass without clusters (dot drops flat\n// ordering inside clusters), then neato -n keeps the pins, draws the clusters and routes the edges.")
for n,(x,y) in pos.items():
    out=re.sub(r'(\n\s+%s\s+\[)'%n, r'\1pos="%.1f,%.1f!", '%(x,y), out, count=1)
open(out_p,"w").write(out); print("pinned",len(pos),"nodes; gap",gap)
