import cairo, math, subprocess, json, sys, re
DOT, OUT = sys.argv[1], sys.argv[2]
J = json.loads(subprocess.run(["dot","-Tjson",DOT],capture_output=True,text=True).stdout)
W,H = [float(v) for v in J["bb"].split(",")][2:]
FONT="DejaVu Sans"; P=24
def hx(c):
    c=c or "#000000"
    if c.startswith("#"): c=c[1:]; return tuple(int(c[i:i+2],16)/255 for i in (0,2,4))
    return {"white":(1,1,1),"black":(0,0,0),"none":(1,1,1)}.get(c,(0,0,0))
g2n={}; nodes={}; clusters=[]
for o in J.get("objects",[]):
    g2n[o["_gvid"]]=o.get("name","")
    nm=o.get("name","")
    if "pos" in o:
        x,y=[float(v) for v in o["pos"].split(",")]
        nodes[nm]=dict(x=x,y=y,w=float(o.get("width",1))*72,h=float(o.get("height",.5))*72,
            label=o.get("label",nm),fill=o.get("fillcolor","#ffffff"),border=o.get("color","#000000"),
            shape=o.get("shape","box"),pen=float(o.get("penwidth",1) or 1),fc=o.get("fontcolor","#000000"),style=o.get("style",""),fs=float(o.get("fontsize",14) or 14))
    elif nm.startswith("cluster"):
        clusters.append(dict(bb=[float(v) for v in o["bb"].split(",")],label=o.get("label",""),
            fill=o.get("bgcolor","#f8fafc"),border=o.get("color","#94a3b8")))
edges=[]
for e in J.get("edges",[]):
    pts=[]; end=None; start=None
    for tk in e.get("pos","").split():
        if tk.startswith("e,"): _,a,b=tk.split(","); end=(float(a),float(b))
        elif tk.startswith("s,"): _,a,b=tk.split(","); start=(float(a),float(b))
        else: a,b=tk.split(","); pts.append((float(a),float(b)))
    if end: pts.append(end)
    if start: pts.insert(0,start)
    edges.append(dict(tl=g2n[e["tail"]],hd=g2n[e["head"]],pts=pts,label=e.get("label",""),
        color=e.get("color","#64748b"),style=e.get("style",""),pen=float(e.get("penwidth",1) or 1),
        dir=e.get("dir",""),fc=e.get("fontcolor","")))
def Y(y): return H-y
# ---- channel centring: ortho hugs obstacles; slide each axis-aligned segment to the middle of its free channel ----
def simplify(pts):
    out=[]
    for q in pts:
        if out and abs(q[0]-out[-1][0])<0.5 and abs(q[1]-out[-1][1])<0.5: continue
        out.append(q)
    i=1
    while i<len(out)-1:
        a,b,c=out[i-1],out[i],out[i+1]
        if (abs(a[0]-b[0])<0.5 and abs(b[0]-c[0])<0.5) or (abs(a[1]-b[1])<0.5 and abs(b[1]-c[1])<0.5): out.pop(i)
        else: i+=1
    return out
MINM=0.4*72
def centre_routes():
    boxes={nm:(n["x"]-n["w"]/2,n["y"]-n["h"]/2,n["x"]+n["w"]/2,n["y"]+n["h"]/2) for nm,n in nodes.items() if "invis" not in (n["style"] or "")}
    placed=[]   # (orientation, coord, lo, hi) of segments already fixed
    for e in edges:
        if e["style"]=="invis" or len(e["pts"])<2: continue
        p=simplify(e["pts"]); e["pts"]=p
        for i in range(len(p)-1):
            a,b=p[i],p[i+1]; vert=abs(a[0]-b[0])<0.5
            k=0 if vert else 1; o=1-k              # k = the coordinate we may slide, o = the along-axis
            c=a[k]; lo,hi=min(a[o],b[o])-8,max(a[o],b[o])+8
            L,R=-P+10,(W if vert else H)+P-10
            for nm,bx in boxes.items():
                if vert: x1,y1,x2,y2=bx
                else:    y1,x1,y2,x2=bx            # swap roles so 'x' is the slide axis
                if y2<lo or y1>hi: continue         # no overlap along the segment
                if nm in (e["tl"],e["hd"]) and (i==0 or i==len(p)-2):
                    # terminal segment: slide only inside this node's face span
                    if (i==0 and nm==e["tl"]) or (i==len(p)-2 and nm==e["hd"]):
                        if x1-0.5<=c<=x2+0.5: L,R=max(L,x1+10),min(R,x2-10); continue
                if x2<=c+0.5: L=max(L,x2)
                elif x1>=c-0.5: R=min(R,x1)
                else: L=R=c                          # inside a box: leave it alone
            if R-L<2*MINM and min(c-L,R-c)>=MINM: continue
            nc=(L+R)/2 if R-L<6*MINM else max(L+MINM+12, min(R-MINM-12, c))   # wide channel: just guarantee the margin
            if abs(nc-c)<1: continue
            # avoid stacking onto an already placed parallel segment
            for (v2,c2,lo2,hi2) in placed:
                if v2==vert and not (hi2<lo or lo2>hi) and abs(c2-nc)<10:
                    nc = c2+12 if c2+12<=R-6 else c2-12
            p[i]=(nc,a[o]) if vert else (a[o],nc); p[i+1]=(nc,b[o]) if vert else (b[o],nc)
            placed.append((vert,nc,lo,hi))
        e["pts"]=p
centre_routes()
json.dump({"W":W,"H":H,"nodes":{nm:dict(x=n["x"],y=n["y"],w=n["w"],h=n["h"]) for nm,n in nodes.items() if "invis" not in (n["style"] or "")},
           "edges":[dict(tl=e["tl"],hd=e["hd"],pts=e["pts"],label=e["label"]) for e in edges if e["style"]!="invis"]},open(OUT+".routes.json","w"))
def rrect(ctx,x,y,w,h,r=4):
    ctx.new_sub_path()
    for cx,cy,a1,a2 in [(x+w-r,y+r,-math.pi/2,0),(x+w-r,y+h-r,0,math.pi/2),(x+r,y+h-r,math.pi/2,math.pi),(x+r,y+r,math.pi,1.5*math.pi)]:
        ctx.arc(cx,cy,r,a1,a2)
    ctx.close_path()
def diamond(ctx,cx,cy,hw,hh): ctx.move_to(cx,cy-hh);ctx.line_to(cx+hw,cy);ctx.line_to(cx,cy+hh);ctx.line_to(cx-hw,cy);ctx.close_path()
def ell(ctx,cx,cy,rx,ry):
    ctx.save();ctx.translate(cx,cy);ctx.scale(rx,ry);ctx.arc(0,0,1,0,2*math.pi);ctx.restore()
def lines(label): return [l for l in re.split(r'\\[lnr]|\n',label)]
def txt(ctx,cx,cy,label,size,bold,color):
    ctx.select_font_face(FONT,0,cairo.FONT_WEIGHT_BOLD if bold else 0); ctx.set_font_size(size); ctx.set_source_rgb(*color)
    L=[l for l in lines(label) if l!=""]; lh=size*1.18; y0=cy-lh*len(L)/2+lh*0.78
    for i,ln in enumerate(L):
        xb,yb,tw,th,_,_=ctx.text_extents(ln); ctx.move_to(cx-tw/2-xb,y0+i*lh); ctx.text_path(ln); ctx.fill()
DIM=(0.42,0.45,0.50)
def ntxt(ctx,cx,cy,label,size,color):
    """Node text: line 1 = bold title; '~' lines = dim annotation at 0.82 size; others regular."""
    L=[l for l in lines(label) if l!=""]
    if not L: return
    spec=[]
    for i,ln in enumerate(L):
        if ln.startswith("~"): spec.append((ln[1:].strip(),size*0.82,False,DIM))
        else: spec.append((ln,size,i==0,color))
    hs=[s*1.18 for _,s,_,_ in spec]; total=sum(hs); y=cy-total/2
    for (ln,s,b,c),h in zip(spec,hs):
        ctx.select_font_face(FONT,0,cairo.FONT_WEIGHT_BOLD if b else 0); ctx.set_font_size(s); ctx.set_source_rgb(*c)
        xb,yb,tw,th,_,_=ctx.text_extents(ln); ctx.move_to(cx-tw/2-xb,y+h*0.78); ctx.text_path(ln); ctx.fill(); y+=h
def chip(ctx,cx,cy,label,size,color):
    ctx.select_font_face(FONT,0,0); ctx.set_font_size(size)
    L=[l for l in lines(label) if l!=""]
    if not L: return
    mw=max(ctx.text_extents(l)[2] for l in L); lh=size*1.18; bh=lh*len(L)
    ctx.set_source_rgb(1,1,1); ctx.rectangle(cx-mw/2-3,cy-bh/2-1,mw+6,bh+2); ctx.fill()
    txt(ctx,cx,cy,label,size,False,color)
def arrow(ctx,pf,pt,color,s=8):
    a=math.atan2(pt[1]-pf[1],pt[0]-pf[0]); ctx.save();ctx.translate(*pt);ctx.rotate(a)
    ctx.move_to(0,0);ctx.line_to(-s,-s*0.42);ctx.line_to(-s,s*0.42);ctx.close_path();ctx.set_source_rgb(*color);ctx.fill();ctx.restore()
def place_chips(ctx,pending):
    ctx.select_font_face(FONT,0,0); ctx.set_font_size(9)
    boxes=[(n["x"]-n["w"]/2,Y(n["y"])-n["h"]/2,n["x"]+n["w"]/2,Y(n["y"])+n["h"]/2) for n in nodes.values() if "invis" not in (n["style"] or "")]
    placed=[]
    def rect(cx,cy,tw,th): return (cx-tw/2-3,cy-th/2-1,cx+tw/2+3,cy+th/2+1)
    def hits(r):
        return any(not (r[2]<b[0] or r[0]>b[2] or r[3]<b[1] or r[1]>b[3]) for b in boxes+placed)
    for e,p in pending:
        L=[l for l in lines(e["label"]) if l]; tw=max(ctx.text_extents(l)[2] for l in L); th=9*1.18*len(L)
        segs=sorted(((p[i],p[i+1]) for i in range(len(p)-1)),key=lambda s:-((s[0][0]-s[1][0])**2+(s[0][1]-s[1][1])**2))
        best=None
        for a,b in segs:
            for t in (0.5,0.4,0.6,0.3,0.7,0.2,0.8):
                cx,cy=a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]); r=rect(cx,cy,tw,th)
                if not hits(r): best=(cx,cy,r); break
            if best: break
        if not best:
            a,b=segs[0]; cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2; best=(cx,cy,rect(cx,cy,tw,th))
        placed.append(best[2]); chip(ctx,best[0],best[1],e["label"],9,hx(e["fc"] or e["color"]))
CHIPS=[]
def draw(ctx):
    pending=[]
    ctx.set_source_rgb(1,1,1);ctx.rectangle(0,0,W+2*P,H+2*P);ctx.fill();ctx.translate(P,P)
    for c in clusters:
        x1,y1,x2,y2=c["bb"]; x1-=12; x2+=12; y1-=10; y2+=26; rrect(ctx,x1,Y(y2),x2-x1,y2-y1,8)
        ctx.set_source_rgb(*hx(c["fill"]));ctx.fill_preserve();ctx.set_source_rgb(*hx(c["border"]));ctx.set_line_width(1.5);ctx.stroke()
        txt(ctx,(x1+x2)/2,Y(y2)+15,c["label"],13,True,hx("#475569"))
    for e in edges:
        if e["style"]=="invis" or len(e["pts"])<2: continue
        p=[(x,Y(y)) for x,y in e["pts"]]
        ctx.set_source_rgb(*hx(e["color"]));ctx.set_line_width(max(e["pen"]*1.2,1.2))
        ctx.set_dash([6,4] if e["style"]=="dashed" else [])
        ctx.move_to(*p[0])
        for q in p[1:]: ctx.line_to(*q)
        ctx.stroke();ctx.set_dash([])
        if e["dir"] in ("","forward","both"): arrow(ctx,p[-2],p[-1],hx(e["color"]))
        if e["dir"] in ("both","back"): arrow(ctx,p[1],p[0],hx(e["color"]))
        if e["label"]: pending.append((e,p))
    place_chips(ctx,pending)
    for nm,n in nodes.items():
        if "invis" in (n["style"] or ""): continue
        cx,cy,w,h=n["x"],Y(n["y"]),n["w"],n["h"]; sh=n["shape"]
        mk=lambda: (diamond(ctx,cx,cy,w/2,h/2) if sh=="diamond" else ell(ctx,cx,cy,w/2,h/2) if sh=="ellipse" else rrect(ctx,cx-w/2,cy-h/2,w,h,4))
        mk();ctx.set_source_rgb(*hx(n["fill"]));ctx.fill_preserve();ctx.set_source_rgb(*hx(n["border"]));ctx.set_line_width(max(n["pen"]*1.1,1));ctx.stroke()
        ntxt(ctx,cx,cy,n["label"],n["fs"],hx(n["fc"]))
    txt(ctx,W/2,18,J.get("label",""),20,True,hx("#0f172a"))
svg=cairo.SVGSurface(OUT+".svg",W+2*P,H+2*P);draw(cairo.Context(svg));svg.finish()
S=2;png=cairo.ImageSurface(cairo.FORMAT_ARGB32,int((W+2*P)*S),int((H+2*P)*S));c=cairo.Context(png);c.scale(S,S);draw(c);png.write_to_png(OUT+".png")
print("rendered",OUT,f"{int(W)}x{int(H)}pt")
