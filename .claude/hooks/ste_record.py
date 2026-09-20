#!/usr/bin/env python3
"""Stop hook, NON-blocking: grade the turn's final assistant text for ASD-STE100 and record violations
to a file. Prints nothing, never blocks -> no second reply, no duplicate in the terminal.
The companion UserPromptSubmit hook (ste_feedback.py) hands the record to the model on the next turn."""
import sys, json, re, os

BANNED = ["wire", "seam", "load-bearing", "sieve"]; MAXWORDS = 20
REC = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "/root/groundstation"), ".claude", "hooks", ".ste_last_violations")

def violations(text):
    prose = re.sub(r"```.*?```", " ", text, flags=re.S); prose = re.sub(r"`[^`]*`", " ", prose)
    prose = re.sub(r"\$\$.*?\$\$", " ", prose, flags=re.S); prose = re.sub(r"\$[^$\n]*\$", " ", prose)
    prose = re.sub(r"\n\s*\n", ". ", prose)
    prose = "\n".join(l for l in prose.split("\n") if not l.lstrip().startswith(("|", "#")))
    out = [f"banned word '{w}'" for w in BANNED if re.search(r"\b" + re.escape(w) + r"\b", prose, re.I)]
    for raw in re.split(r"(?<=[.!?:])\s+", prose):
        s = raw.strip()
        if not s or s[0] in "-*>" or "http" in s: continue
        n = len(re.findall(r"\b[\w'-]+\b", s))
        if n > MAXWORDS: out.append(f"{n}-word sentence: \"{s[:70]}...\"")
    return out

def main():
    try: data = json.load(sys.stdin)
    except Exception: sys.exit(0)
    last = data.get("last_assistant_message") or ""
    if not isinstance(last, str) or not last.strip(): sys.exit(0)
    v = violations(last)
    try:
        if v:
            open(REC, "w").write("\n".join(v[:8]))
        elif os.path.exists(REC):
            os.remove(REC)
    except Exception: pass
    sys.exit(0)                                     # never block, never print

if __name__ == "__main__": main()
