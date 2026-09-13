import re,sys
for p in sys.argv[1:]:
    s=open(p).read()
    s=re.sub(r'rgb\(([0-9.,%\s]+)\)', lambda m:'#%02x%02x%02x'%tuple(round(float(x)*255/100) for x in m.group(1).replace('%','').split(',')), s)
    s=re.sub(r'\d+\.\d{2,}', lambda m:f"{float(m.group(0)):.1f}", s)
    open(p,'w').write(s)
