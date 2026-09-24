"""refill(path, first_line_substring): reflow the ONE docstring that starts on the line holding
the substring. Paragraphs split on blank lines; a line starting with 2+ spaces after the
docstring indent, '- ', '@' or a word followed by '->' starts its own item, whose continuation
lines hang under its text. Width 89."""
import ast, re, sys, textwrap
W = 89
ITEM = re.compile(r"^(\s*)(- |@\w+:? |\w[\w /|]*?\s+-> )")


def refill(path, needle):
    src = open(path, encoding="utf-8").read()
    t = ast.parse(src)
    L = src.split("\n")
    for n in ast.walk(t):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant) \
                and isinstance(n.body[0].value.value, str) \
                and needle in L[n.body[0].lineno - 1]:
            d = n.body[0]
            a, b, col = d.lineno - 1, d.end_lineno, d.col_offset
            break
    else:
        raise SystemExit(f"no docstring with {needle!r} in {path}")
    block = L[a:b]
    q = block[0].index('"""')
    head = block[0][:q + 3]
    lines = [block[0][q + 3:]] + [x[col:] if x[:col].strip() == "" else x.lstrip() for x in block[1:]]
    lines[-1] = lines[-1][:lines[-1].rindex('"""')]
    ind = " " * col
    out, item, item_lead, hang = [], [], "", ""

    def flush():
        if not item:
            return
        text = " ".join(x.strip() for x in item)
        first = (head if not out else ind) + item_lead
        out.extend(textwrap.wrap(text, W, initial_indent=first, subsequent_indent=ind + hang,
                                 break_long_words=False, break_on_hyphens=False) or [first])
    for x in lines:
        if not x.strip():
            flush(); item = []
            out.append("" if out else head)
            continue
        m = ITEM.match(x)
        lead_sp = len(x) - len(x.lstrip())
        if m or (lead_sp >= 2 and not item):
            flush()
            item_lead = x[:lead_sp]
            hang = " " * (lead_sp + (len(m.group(2)) if m else 0))
            item = [x[lead_sp:]]
        elif item and lead_sp >= len(hang) and hang:
            item.append(x)
        elif item and not hang:
            item.append(x)
        else:
            flush()
            item_lead, hang = x[:lead_sp], " " * lead_sp
            item = [x[lead_sp:]]
    flush()
    if len(out[-1]) + 3 > W:                       # the closing quotes must fit too
        words = out[-1].split(" ")
        out[-1] = " ".join(words[:-1])
        out.append(ind + hang + words[-1])
    out[-1] = out[-1] + '"""'
    L[a:b] = out
    open(path, "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    refill(sys.argv[1], sys.argv[2])
