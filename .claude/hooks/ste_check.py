#!/usr/bin/env python3
"""Stop hook: check the assistant's last message follows ASD-STE100 (short sentences, no banned words).
Blocks the stop with the specific violations so the model rewrites. Owner-installed 2026-09-19."""
import sys, json, re

BANNED = ["wire", "seam", "load-bearing", "sieve"]
MAXWORDS = 20

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("stop_hook_active"):            # already re-prompted once this turn; do not loop
        sys.exit(0)
    tp = data.get("transcript_path")
    if not tp:
        sys.exit(0)
    last = ""
    try:
        with open(tp) as f:
            for line in f:
                try: ev = json.loads(line)
                except Exception: continue
                if ev.get("type") == "assistant":
                    content = ev.get("message", {}).get("content", [])
                    txt = "".join(p.get("text", "") for p in content
                                  if isinstance(p, dict) and p.get("type") == "text")
                    if txt.strip():
                        last = txt
    except Exception:
        sys.exit(0)
    if not last.strip():
        sys.exit(0)
    prose = re.sub(r"```.*?```", " ", last, flags=re.S)   # drop fenced code
    prose = re.sub(r"`[^`]*`", " ", prose)                # drop inline code
    viol = []
    for w in BANNED:
        if re.search(r"\b" + re.escape(w) + r"\b", prose, re.I):
            viol.append(f"banned word: '{w}'")
    for raw in re.split(r"(?<=[.!?])\s+", prose):
        s = raw.strip()
        if not s or s[0] in "#|-*>" or "http" in s:
            continue
        n = len(re.findall(r"\b[\w'-]+\b", s))
        if n > MAXWORDS:
            viol.append(f"sentence has {n} words (max {MAXWORDS}): \"{s[:55]}...\"")
    if viol:
        reason = ("Your last message breaks ASD-STE100. Rewrite it: sentences <=20 words, one idea "
                  "each, plain words, no banned words. Fix these and resend:\n- " + "\n- ".join(viol[:10]))
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)

if __name__ == "__main__":
    main()
