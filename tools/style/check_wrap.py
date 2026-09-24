"""Check a wrapped file against its backup: the program must be identical (AST equal; docstrings
compared with whitespace collapsed) and no line may exceed 89 characters.
Usage: python3 check_wrap.py <file> [<file> ...]   (run from projects/integration_harden2)
Backup root: /tmp/claude-0/harden2-before-wrap"""
import ast, os, sys

BACKUP = "/tmp/claude-0/harden2-before-wrap"
MAX = 89


def norm(src):
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            d = n.body[0]
            if isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) and isinstance(d.value.value, str):
                d.value.value = " ".join(d.value.value.split())
    return ast.dump(t)


bad = 0
for f in sys.argv[1:]:
    new = open(f, encoding="utf-8").read()
    old = open(os.path.join(BACKUP, f), encoding="utf-8").read()
    msgs = []
    try:
        if norm(new) != norm(old):
            msgs.append("PROGRAM CHANGED (AST differs)")
    except SyntaxError as e:
        msgs.append(f"SYNTAX ERROR {e}")
    long = [i for i, l in enumerate(new.split("\n"), 1) if len(l) > MAX]
    if long:
        msgs.append(f"{len(long)} lines > {MAX}: {long[:15]}")
    if msgs:
        bad += 1
        print(f, "; ".join(msgs))
print("OK" if not bad else f"{bad} file(s) not done")
