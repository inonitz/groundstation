#!/usr/bin/env python3
"""Lay out the API headers by docs/guidelines.md: one member per line, members aligned, field
notes in an "@field:" block above the struct, one enum value per line, one argument per line in
a long prototype, a blank line between declarations. Usage: header_layout.py FILE.h [...]"""
import re
import sys
import textwrap

LIMIT = 89


def split_top(text, sep):
    """Split at `sep` outside any parentheses or braces."""
    parts = []
    depth = 0
    cur = ""
    for ch in text:
        if ch in "({":
            depth += 1
        if ch in ")}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def member_name(decl):
    m = re.search(r"\(\*\s*(\w+)\)", decl)
    if m:
        return m.group(1)
    m = re.search(r"(\w+)\s*(?:\[[^\]]*\])?\s*$", decl)
    return m.group(1) if m else decl


def declarators(decl):
    """'float x0, y0' -> ['float x0', 'float y0']: one member per line."""
    if "(" in decl or "{" in decl or "," not in decl:
        return [decl]
    first, *rest = [part.strip() for part in decl.split(",")]
    kind = first.rsplit(" ", 1)[0]
    return [first] + [kind + " " + name for name in rest]


def note_block(notes):
    if not notes:
        return []
    out = ["/*"]
    for name, text in notes:
        out.append(f" * @{name}:")
        for line in textwrap.wrap(" ".join(text.split()), LIMIT - 7):
            out.append(" *     " + line)
    out.append(" */")
    return out


def clean(comment):
    return comment.replace("/*", " ").replace("*/", " ").strip().strip("*").strip()


def lay_struct(head, body, tail):
    """head: 'typedef struct X {' / 'struct X {'; body: its lines; tail: '} X;' / '};'."""
    members = []        # [decl, note]
    lead = ""
    in_lead = False
    open_note = False
    for raw in body:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        deep = len(line) - len(line.lstrip("\t")) > 0 and line.lstrip("\t").startswith(" ")
        if in_lead:
            lead += " " + clean(s)
            in_lead = "*/" not in s
            continue
        if open_note or (s.startswith("/*") and deep and members):
            members[-1][1] += " " + clean(s)
            open_note = "*/" not in s
            continue
        if s.startswith("/*"):
            lead += " " + clean(s)
            in_lead = "*/" not in s
            continue
        code, _, comment = s.partition("/*")
        decls = [code.strip().rstrip(";")] if "union {" in code else split_top(code, ";")
        decls = [one for decl in decls for one in declarators(decl)]
        for i, decl in enumerate(decls):
            note = ""
            if i == 0:
                note = (lead + " " + clean(comment)).strip()
                lead = ""
            members.append([decl, note])
        open_note = bool(comment) and "*/" not in comment
    notes = [(member_name(d), n) for d, n in members if n]
    simple = [d for d, _ in members if "(" not in d and "{" not in d]
    width = 0
    for d in simple:
        width = max(width, len(d.rsplit(" ", 1)[0]))
    out = note_block(notes) + [head]
    for d, _ in members:
        if d in simple:
            kind, name = d.rsplit(" ", 1)
            out.append("\t" + kind.ljust(width) + " " + name + ";")
        else:
            out.append("\t" + " ".join(d.split()) + ";")
    out.append(tail)
    return out


def lay_enum(text):
    m = re.match(r"\s*(typedef enum|enum)\s*\{(.*)\}\s*(\w*)\s*;(.*)$", text, re.S)
    body = m.group(2)
    items = []
    for piece in re.findall(r"([^,/]+)((?:\s*/\*.*?\*/)*)\s*,?", body, re.S):
        name = " ".join(piece[0].split())
        if name:
            items.append((name, clean(piece[1])))
    out = []
    after = clean(m.group(4))
    if after:
        out.append("/* " + after + " */")
    notes = [(n.split("=")[0].strip(), c) for n, c in items if c]
    out += note_block(notes)
    out.append(m.group(1) + " {")
    for i, (name, _) in enumerate(items):
        out.append("\t" + name + ("," if i < len(items) - 1 else ""))
    out.append("} " + m.group(3) + ";" if m.group(3) else "};")
    return out


def lay_proto(text):
    code, _, comment = text.partition("/*")
    code = " ".join(code.split())
    note = clean(comment)
    one = code + ("   /* " + note + " */" if note else "")
    if len(one.expandtabs(4)) <= LIMIT:
        return [one]
    out = []
    if note:
        out += ["/* " + line + " */" for line in textwrap.wrap(note, LIMIT - 6)]
    if len(code) <= LIMIT:
        return out + [code]
    m = re.match(r"(.*?\w)\((.*)\);$", code)
    if not m or code.startswith("typedef"):
        return out + [code]
    args = split_top(m.group(2), ",")
    out.append(m.group(1) + "(")
    for i, arg in enumerate(args):
        out.append("\t" + arg + ("," if i < len(args) - 1 else ""))
    out.append(");")
    return out


def gap(out):
    """A blank line before a declaration, unless its own comment is right above it."""
    if out and out[-1].strip().endswith("*/"):
        return []
    return [""]


DIAGRAM = re.compile(r"[|+]|-->|==|<--")


LABEL = re.compile(r"^(\d+\.|-|[A-Za-z@][^:]{0,24}:)\s")


def reflow(block):
    """One block comment as paragraphs, wrapped as a whole. A line that starts with a
    label ("1.", "-", "COUNT:", "manual = true:") starts a new paragraph."""
    indent = block[0][:len(block[0]) - len(block[0].lstrip())]
    paragraphs = []
    for line in block:
        text = clean(line.strip())
        if not text:
            paragraphs.append("")
            continue
        if not paragraphs or paragraphs[-1] == "" or LABEL.match(text):
            paragraphs.append(text)
            continue
        paragraphs[-1] += " " + text
    width = LIMIT - len(indent.expandtabs(4)) - 4
    out = []
    for paragraph in paragraphs:
        if not paragraph:
            out.append("")
            continue
        hang = "    " if LABEL.match(paragraph) else ""
        out += textwrap.wrap(
            " ".join(paragraph.split()),
            width,
            subsequent_indent=hang,
            break_long_words=False,
            break_on_hyphens=False
        )
    laid = [indent + ("/* " if k == 0 else " * ") + text for k, text in enumerate(out)]
    laid[-1] += " */"
    return [line.rstrip() if line.strip() != "*" else indent + " *" for line in laid]


def wrap_comments(lines):
    """A block comment with a line over the limit is reflowed; a drawing, a field-note block
    and a file's opening block are left as written."""
    out = []
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("/*"):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while "*/" not in lines[j]:
            j += 1
        block = lines[i:j + 1]
        too_long = any(len(line.expandtabs(4)) > LIMIT for line in block)
        keep = any(DIAGRAM.search(line) or "@" in line for line in block)
        out += block if (not too_long or keep) else reflow(block)
        i = j + 1
    return out


def lay(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("/*") and "*/" not in s:            # a block comment: keep it
            while "*/" not in lines[i]:
                out.append(lines[i])
                i += 1
            out.append(lines[i])
            i += 1
            continue
        if re.match(r"(typedef )?enum\b.*\{", s):
            j = i
            while not re.search(r"\}\s*\w*\s*;", lines[j]):
                j += 1
            out += gap(out) + lay_enum("\n".join(lines[i:j + 1])) + [""]
            i = j + 1
            continue
        if re.match(r"typedef struct\s*\w*\s*\{\s*[^/\s]", s):  # members on the head line
            while not re.search(r"\}\s*\w+;", s):
                i += 1
                s += " " + lines[i].strip()
        one = re.match(r"(typedef struct\s*\w*\s*\{)(.*)(\}\s*\w+;)(.*)$", s)
        if one:                                             # a struct written on one line
            after = clean(one.group(4))
            if after:
                out.append("/* " + after + " */")
            out += gap(out) + lay_struct(one.group(1), [one.group(2)], one.group(3)) + [""]
            i += 1
            continue
        if re.match(r"(typedef )?struct\b[^;]*\{", s):
            head, _, comment = s.partition("/*")
            if clean(comment):
                out.append("/* " + clean(comment) + " */")
            j = i + 1
            while not lines[j].startswith("}"):
                j += 1
            out += gap(out) + lay_struct(head.strip(), lines[i + 1:j], lines[j].strip()) + [""]
            i = j + 1
            continue
        if "(" in s and not s.startswith(("#", "*", "/", "typedef struct", "extern")):
            j = i
            joined = s
            while ";" not in joined.partition("/*")[0]:
                j += 1
                joined += " " + lines[j].strip()
            while joined.count("/*") > joined.count("*/"):   # a comment that runs on
                j += 1
                joined += " " + lines[j].strip()
            out += lay_proto(joined)
            i = j + 1
            continue
        out.append(line)
        i += 1
    text = "\n".join(wrap_comments(align_prototypes(out)))
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"


PROTO = re.compile(r"^(\w[\w \*]*?[ \*])(\w+\(.*)$")


def align_prototypes(lines):
    """Consecutive one-line prototypes get their names in one column."""
    out = []
    run = []

    def flush():
        width = max((len(m.group(1).rstrip()) for m in run), default=0)
        padded = [m.group(1).rstrip().ljust(width) + " " + m.group(2) for m in run]
        if any(len(p.expandtabs(4)) > LIMIT for p in padded):
            padded = [m.group(0) for m in run]
        out.extend(padded)
        run.clear()
        return

    for line in lines:
        m = PROTO.match(line)
        if m and not line.startswith(("typedef", "extern", "#")):
            run.append(m)
            continue
        flush()
        out.append(line)
    flush()
    return out


def main():
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        laid = lay(text)                 # first: a failure here must not empty the file
        with open(path, "w", encoding="utf-8") as f:
            f.write(laid)
    return


if __name__ == "__main__":
    main()
