#!/usr/bin/env python3
"""Stop hook: check the assistant's CURRENT message follows ASD-STE100 (sentences <= 20 words,
no banned words). Blocks the stop with the violations so the model rewrites. Owner-installed 2026-09-19.
2026-09-19 fix: grade only the current turn. Prefer `last_assistant_message` from the hook input;
else take assistant text written AFTER the last user event in the transcript. A stale transcript
(new message not yet flushed) yields no text -> no check, never a check of an older message.
Also strips $...$ / $$...$$ math and treats blank lines as sentence ends."""
import sys, json, re, os

BANNED = ["wire", "seam", "load-bearing", "sieve"]
MAXWORDS = 20
DUMP = os.environ.get("STE_CHECK_DUMP")   # set to a path to record the hook input keys once

def current_turn_text(tp):
    turn = []
    try:
        with open(tp) as f:
            for line in f:
                try: ev = json.loads(line)
                except Exception: continue
                t = ev.get("type")
                if t == "user":
                    c = ev.get("message", {}).get("content", "")
                    is_tool_result = isinstance(c, list) and any(
                        isinstance(p, dict) and p.get("type") == "tool_result" for p in c)
                    if not is_tool_result:
                        turn = []              # a real user message starts a new turn
                elif t == "assistant":
                    c = ev.get("message", {}).get("content", [])
                    txt = "".join(p.get("text", "") for p in c
                                  if isinstance(p, dict) and p.get("type") == "text")
                    if txt.strip():
                        turn.append(txt)
    except Exception:
        return ""
    return turn[-1] if turn else ""

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if DUMP:
        try:
            with open(DUMP, "a") as f:
                f.write(json.dumps({k: (v if k != "last_assistant_message" else str(v)[:80])
                                    for k, v in data.items()}) + "\n")
        except Exception:
            pass
    if data.get("stop_hook_active"):
        sys.exit(0)
    last = data.get("last_assistant_message") or ""
    if not isinstance(last, str):
        last = ""
    if not last.strip() and data.get("transcript_path"):
        last = current_turn_text(data["transcript_path"])
    if not last.strip():
        sys.exit(0)
    prose = re.sub(r"```.*?```", " ", last, flags=re.S)     # fenced code
    prose = re.sub(r"`[^`]*`", " ", prose)                  # inline code
    prose = re.sub(r"\$\$.*?\$\$", " ", prose, flags=re.S)  # display math
    prose = re.sub(r"\$[^$\n]*\$", " ", prose)              # inline math
    prose = re.sub(r"\n\s*\n", ". ", prose)                 # paragraph break ends a sentence
    prose = "\n".join(l for l in prose.split("\n") if not l.lstrip().startswith(("|","#")))  # drop table rows, headers
    viol = []
    for w in BANNED:
        if re.search(r"\b" + re.escape(w) + r"\b", prose, re.I):
            viol.append(f"banned word: '{w}'")
    for raw in re.split(r"(?<=[.!?:])\s+", prose):
        s = raw.strip()
        if not s or s[0] in "#|-*>" or "http" in s:
            continue
        n = len(re.findall(r"\b[\w'-]+\b", s))
        if n > MAXWORDS:
            viol.append(f'sentence has {n} words (max {MAXWORDS}): "{s[:55]}..."')
    if viol:
        reason = ("Your last message breaks ASD-STE100. Rewrite it: sentences <=20 words, one idea each, "
                  "plain words, no banned words. Fix these and resend:\n- " + "\n- ".join(viol[:10]))
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)

if __name__ == "__main__":
    main()
