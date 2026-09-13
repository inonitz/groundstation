"""Margins from dot -Tplain (inches): min distance of every edge route to every non-endpoint node.
Also: text overflow (cairo extents vs node width) and PNG ink coverage."""
import subprocess,sys,math,re,cairo
dot=sys.argv[1]; png=sys.argv[2] if len(sys.argv)>2 else None
P=subprocess.run(["dot","-Tplain",dot],capture_output=True,text=True).stdout.splitlines()
nodes={};edges=[]
for l in P:
    t=l.split()
    if not t: continue
    if t[0]=="node": nodes[t[1]]=(float(t[2]),float(t[3]),float(t[4]),float(t[5]))
    elif t[0]=="edge":
        n=int(t[3]); pts=[(float(t[4+2*i]),float(t[5+2*i])) for i in range(n)]
        if "invis" in t[-2]: continue
        edges.append((t[1],t[2],pts))
def dseg(p,a,b):
    ax,ay=a;bx,by=b;px,py=p;dx,dy=bx-ax,by-ay;L=dx*dx+dy*dy
    t=0 if L==0 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L)); cx,cy=ax+t*dx,ay+t*dy
    return math.hypot(px-cx,py-cy)
def rect_seg(r,a,b):
    x,y,w,h=r; x1,y1,x2,y2=x-w/2,y-h/2,x+w/2,y+h/2
    # sample the segment densely; distance from a point to the rectangle (0 inside)
    best=1e9
    for i in range(41):
        t=i/40; px=a[0]+t*(b[0]-a[0]); py=a[1]+t*(b[1]-a[1])
        ddx=max(x1-px,0,px-x2); ddy=max(y1-py,0,py-y2); best=min(best,math.hypot(ddx,ddy))
    return best
import os,json as _j
rj=(png or dot).rsplit(".",1)[0]+".routes.json"
if os.path.exists(rj):
    R=_j.load(open(rj)); nodes={k:(v["x"]/72,v["y"]/72,v["w"]/72,v["h"]/72) for k,v in R["nodes"].items()}
    edges=[(e["tl"],e["hd"],[(x/72,y/72) for x,y in e["pts"]]) for e in R["edges"]]; print("(margins from the rendered routes)")
bad=[]
for tl,hd,pts in edges:
    for nm,r in nodes.items():
        if nm in (tl,hd) or nm.startswith("_"): continue
        m=min(rect_seg(r,pts[i],pts[i+1]) for i in range(len(pts)-1))
        if m<0.4: bad.append((round(m,2),tl,hd,nm))
bad.sort()
# parallel edge segments closer than 0.08in with overlapping extent = stacked lines
segs=[]
for tl,hd,pts in edges:
    for i in range(len(pts)-1):
        a,b=pts[i],pts[i+1]; v=abs(a[0]-b[0])<0.01
        segs.append((f"{tl}->{hd}",v,a[0] if v else a[1],min(a[1-(0 if v else 1)] if False else (a[1] if v else a[0]),(b[1] if v else b[0])),max((a[1] if v else a[0]),(b[1] if v else b[0]))))
stack=[]
for i in range(len(segs)):
    for j in range(i+1,len(segs)):
        n1,v1,c1,l1,h1=segs[i]; n2,v2,c2,l2,h2=segs[j]
        if n1.split("->")[0]==n2.split("->")[0] and n1!=n2 and False: pass
        if v1==v2 and abs(c1-c2)<0.08 and min(h1,h2)-max(l1,l2)>0.3 and n1!=n2: stack.append((n1,n2,round(abs(c1-c2),2)))
print("stacked parallel segments:",len(stack)); [print("  ",x) for x in stack[:10]]
# label chips: on the longest segment's midpoint (as the renderer draws them); must not overlap a box or another chip
if os.path.exists(rj):
    import cairo as _c; sf=_c.ImageSurface(_c.FORMAT_ARGB32,4,4); cx=_c.Context(sf); cx.select_font_face("DejaVu Sans"); cx.set_font_size(9)
    chips=[]
    for e in R["edges"]:
        if not e["label"]: continue
        p=e["pts"]; a,b=max(((p[i],p[i+1]) for i in range(len(p)-1)),key=lambda s:(s[0][0]-s[1][0])**2+(s[0][1]-s[1][1])**2)
        mx,my=(a[0]+b[0])/2,(a[1]+b[1])/2; tw=cx.text_extents(e["label"])[2]; th=9*1.18
        chips.append((e["tl"]+"->"+e["hd"],(mx-tw/2-3)/72,(my-th/2-1)/72,(mx+tw/2+3)/72,(my+th/2+1)/72))
    hit=[]
    for nm,x1,y1,x2,y2 in chips:
        for n,(x,y,w,h) in nodes.items():
            if not (x2<x-w/2 or x1>x+w/2 or y2<y-h/2 or y1>y+h/2): hit.append(("chip-vs-box",nm,n))
        for nm2,a1,b1,a2,b2 in chips:
            if nm2>nm and not (x2<a1 or x1>a2 or y2<b1 or y1>b2): hit.append(("chip-vs-chip",nm,nm2))
    print("label chip collisions:",len(hit)); [print("  ",h) for h in hit]
print("margins<0.4in:",len(bad))
for b in bad[:40]: print("  %.2f  %s->%s  near %s"%b)
# text overflow: DejaVu Sans extents (title bold) vs node width in points
import json
J=json.loads(subprocess.run(["dot","-Tjson",dot],capture_output=True,text=True).stdout)
surf=cairo.ImageSurface(cairo.FORMAT_ARGB32,10,10);ctx=cairo.Context(surf)
over=[]
for o in J["objects"]:
    if "pos" not in o: continue
    w=float(o["width"])*72; fs=float(o.get("fontsize",14)); L=[l for l in re.split(r'\\[lnr]|\n',o.get("label","")) if l]
    for i,ln in enumerate(L):
        s=fs*0.82 if ln.startswith("~") else fs; ln=ln.lstrip("~").strip()
        ctx.select_font_face("DejaVu Sans",0,cairo.FONT_WEIGHT_BOLD if i==0 else 0); ctx.set_font_size(s)
        tw=ctx.text_extents(ln)[2]
        if tw>w-8: over.append((o["name"],ln,round(tw),round(w)))
print("text overflow:",len(over))
for x in over: print("  ",x)
bb=[float(v) for v in J["bb"].split(",")]; print("bb in: %.1f x %.1f  aspect %.2f"%(bb[2]/72,bb[3]/72,bb[2]/bb[3]))
if png:
    from PIL import Image; import numpy as np
    im=np.array(Image.open(png).convert("L")); ink=(im<250)
    print("png %dx%d ink %.1f%%  right-margin ink %s  bottom-band ink %s"%(im.shape[1],im.shape[0],100*ink.mean(),ink[:,-20:].any(),ink[-20:,:].any()))
