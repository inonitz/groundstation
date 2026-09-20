#!/usr/bin/env python3
"""UserPromptSubmit hook: if the previous reply broke ASD-STE100, hand the recorded violations to the
model as additionalContext, then clear the record. The user sees nothing extra."""
import sys, json, os
REC = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "/root/groundstation"), ".claude", "hooks", ".ste_last_violations")
try: json.load(sys.stdin)
except Exception: pass
if os.path.exists(REC):
    try:
        v = open(REC).read().strip(); os.remove(REC)
    except Exception:
        v = ""
    if v:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
              "additionalContext": "STE check on your previous reply failed. Do not repeat these in this reply:\n- "
                                   + v.replace("\n", "\n- ") + "\nKeep every sentence under 20 words."}}))
sys.exit(0)
