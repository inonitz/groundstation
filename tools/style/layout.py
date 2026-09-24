"""Fix E701/E704 (one-line compound statements) and E30x (blank lines) from flake8 reports,
proving each file's AST unchanged."""
import ast, collections, subprocess, sys

def report(codes):
    out = subprocess.run([sys.executable, "-m", "flake8", "--isolated", f"--select={codes}",
                          "--exclude=__pycache__", "."], capture_output=True, text=True).stdout
    by = collections.defaultdict(list)
    for line in out.splitlines():
        f, r, c, msg = line.split(":", 3)
        by[f].append((int(r), int(c), msg.strip()))
    return by

def fix(path, items, mode):
    src = open(path, encoding="utf-8").read()
    before = ast.dump(ast.parse(src))
    L = src.split("\n")
    for r, c, msg in sorted(items, reverse=True):
        line = L[r - 1]
        if mode == "colon":
            i = c - 1
            if line[i] != ":":
                continue
            ind = line[:len(line) - len(line.lstrip())]
            L[r - 1:r] = [line[:i + 1], ind + "    " + line[i + 1:].strip()]
        else:
            code = msg.split()[0]
            want = {"E302": 2, "E305": 2, "E301": 1}.get(code)
            j = r - 2                               # count blank lines above
            n = 0
            while j >= 0 and L[j].strip() == "":
                n += 1
                j -= 1
            # comments directly above a def belong to it: blank lines go above the comments
            if code == "E303":
                keep = 2 if not line.startswith(" ") else 1
                del L[r - 1 - n:r - 1 - keep]
            elif want is not None and n < want:
                k = r - 1
                while k - 1 >= 0 and L[k - 1].lstrip().startswith(("#", "@")) and L[k - 1].strip():
                    k -= 1
                for _ in range(want - n):
                    L.insert(k, "")
    out = "\n".join(L)
    assert ast.dump(ast.parse(out)) == before, path
    open(path, "w", encoding="utf-8").write(out)

for _ in range(4):
    by = report("E701,E704")
    for f, items in by.items():
        fix(f, items, "colon")
    by = report("E301,E302,E303,E305")
    for f, items in by.items():
        fix(f, items, "blank")
left = report("E301,E302,E303,E305,E701,E704")
print("left:", sum(len(v) for v in left.values()))
for f, v in left.items():
    print(f, v[:3])
