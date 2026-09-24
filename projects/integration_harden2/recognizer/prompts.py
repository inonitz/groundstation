"""Every prompt, grammar, and few-shot set the recognizer and the bench use, in one
place. After an edit, run `python3 recognizer/prompts.py` to regenerate
recognizer/PROMPTS.md (the owner-readable copy).

LIVE (the app's one Gemma call): UNIFIED_PROMPT + UNIFIED_GRAMMAR + UNIFIED_SHOTS:
Hebrew in, {kind, target_en, mission} out.
Bench precursors: APP_PROMPT = what the phone app ships today (reconstructed from
SpeechResolving.kt:599-635, 5-action subset). REVISED_PROMPT = its replacement (sign
rule + refusal rule; its 6 few-shot pairs ride as chat turns, PLANNER_SHOTS_D).
UNIFIED_PROMPT is built on REVISED_PROMPT."""
import json
import os

# ======== bench precursors: the phone app prompt and its revised scaffold ========

# ---- app prompt, reconstructed. Scaffold: SpeechResolving.kt:599-635. Schema block:
# ---- app's appendPropertyShortJson format
# ---- (desc comment line, "name":  type, (optional) mark),
# ---- restricted to the 5 whitelisted actions.
SCHEMA_5 = '''"takeoff":  object {
\t"type": "takeoff",
},

"land":  object {
\t"type": "land",
},

// Moves aircraft relative to it's current position \
(m). At least one direction must be non zero.
"fly_by":  object {
\t"type": "fly_by",
\t// x+ is forward
\t"dx":  number (optional),
\t// y+ is right
\t"dy":  number (optional),
\t// z+ is up
\t"dz":  number (optional),
\t// -6..6 (m/s)
\t"velocity":  number (optional),
},

// Spins aircraft relative to it's current heading.
"spin_by":  object {
\t"type": "spin_by",
\t"degrees":  number (optional),
},

"delay":  object {
\t"type": "delay",
\t"seconds":  number,
},'''

APP_HEAD = '''# Role

You are a speech-to-intent engine.

The user wants to perform a sequence of one or more actions.

Translate & Convert the user's natural language \
request into a JSON array of system actions.

Each action must exactly match one of the JSON Schemas below.

# Rules

- The JSON Schemas below are the ONLY valid actions.
- Never invent actions or fields. Never rephrase their names.
- Use ONLY the available system actions and fields below.
- Use the EXACT "type" value, field names & enum constants from the schemas.
- Output valid JSON Array only.

# Semantics

- Infer the user's intent and populate schema fields accordingly.
- If field is optional and the user did not explicitly \
or implicitly specify a value, you must omit the field.
- Comments in the input Schema provide each field's semantics. Don't output comments.
- Grammar in request like "x and y", "x then y", "do x, y" hints at multiple actions.
     -- for ex.: "takeoff, fly forward ... then fly \
upwards ... and then ..." is multiple actions.'''

APP_TAIL = '''# Output

Return ONLY the JSON array.'''

APP_PROMPT = APP_HEAD + "\n\n# Available Actions\n" + SCHEMA_5 + "\n\n" + APP_TAIL

# ---- revised prompt = app-prompt scaffold + the three measured deficits fixed:
# ---- (a) verbal->sign map (round-3: 7/14 top-arm fails were "turn right N" -> -N),
# ---- (b) negation/question -> [] rule, (c) few-shot (added separately as chat turns).
REVISED_PROMPT = APP_HEAD + '''

# Signs & Directions (follow EXACTLY)

- fly_by is in the aircraft body frame: dx+ forward, \
dx- backward; dy+ right, dy- left; dz+ up, dz- down.
- spin_by degrees: turning RIGHT = clockwise = POSITIVE \
degrees. Turning LEFT = counterclockwise = NEGATIVE degrees.
  "turn right 20 degrees" -> {"type":"spin_by","degrees":20}. \
"turn left 30 degrees" -> {"type":"spin_by","degrees":-30}.
- A full turn is 360 degrees. Half a turn is 180 degrees.
- Number words ("five", "half a meter") become digits (5, 0.5).

# Refusals

- A negated clause ("don't fly up", "do not land") produces NO action for that clause.
- Questions, status requests, and anything that is \
not a movement command -> output [] (empty array).
- Keep the actions in the exact order the user gave them.

# Available Actions
''' + SCHEMA_5 + "\n\n" + APP_TAIL

PLANNER_SHOTS_D = [
    ("fly left 12 meters", '[{"type":"fly_by","dy":-12}]'),
    ("go down 2 meters then fly forward 6 meters",
     '[{"type":"fly_by","dz":-2},{"type":"fly_by","dx":6}]'),
    ("do not fly up", "[]"),
    ("what's your altitude", "[]"),
    ("turn right 20 degrees", '[{"type":"spin_by","degrees":20}]'),
    ("take off, rise 4 meters, turn 90 degrees clockwise, "
     "fly forward 6 meters, and land",
     '[{"type":"takeoff"},{"type":"fly_by","dz":4},{"type":"spin_by","degrees":90},'
     '{"type":"fly_by","dx":6},{"type":"land"}]'),
]


# == harden2 (2026-09-08): ONE Gemma call routes, plans and names the object for SAM3 ==
# The model reads the Hebrew directly (no translator).
# kind = mission | highlight | count | describe | reject.
# target_en = the object phrase in English for the segmenter (SAM3 reads English only);
# "" when not needed.
# mission = the phone app mission (same schema as the mission grammar); [] unless
# kind == "mission".
# The long rules are split into adjacent raw literals; the joined grammar is unchanged.
UNIFIED_GRAMMAR = (r"""
root ::= "{" ws "\"kind\"" ws ":" ws kind ws "," ws "\"target_en\"" ws ":" ws "\"" """
r"""str "\"" ws "," ws "\"mission\"" ws ":" ws missionarr ws "}"
kind ::= "\"mission\"" | "\"highlight\"" | "\"count\"" | "\"describe\"" | "\"reject\""
str ::= [^"\n\\]*
missionarr ::= "[" ws (action (ws "," ws action)*)? ws "]"
action ::= takeoff | land | flyby | spinby | gimbal | home | wave | delay
takeoff ::= "{" ws "\"type\"" ws ":" ws "\"takeoff\"" ws "}"
land ::= "{" ws "\"type\"" ws ":" ws "\"land\"" ws "}"
flyby ::= "{" ws "\"type\"" ws ":" ws "\"fly_by\"" (ws "," ws axis)+ ws "}"
axis ::= ("\"dx\"" | "\"dy\"" | "\"dz\"" | "\"velocity\"") ws ":" ws num
spinby ::= "{" ws "\"type\"" ws ":" ws "\"spin_by\"" ws "," """
r"""ws "\"degrees\"" ws ":" ws num ws "}"
delay ::= "{" ws "\"type\"" ws ":" ws "\"delay\"" ws "," """
r"""ws "\"seconds\"" ws ":" ws num ws "}"
gimbal ::= "{" ws "\"type\"" ws ":" ws "\"gimbal_pitch\"" ws "," """
r"""ws "\"angle\"" ws ":" ws num ws "}"
home ::= "{" ws "\"type\"" ws ":" ws "\"home\"" ws "}"
wave ::= "{" ws "\"type\"" ws ":" ws "\"wave\"" ws "}"
num ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
""")

UNIFIED_PROMPT = REVISED_PROMPT + """

# Input language and routing (harden2)

- The request is in Hebrew (sometimes with an \
English word inside). Understand it directly.
- Output ONE JSON object: {"kind": ..., "target_en": ..., "mission": [...]}.
- kind = "mission" when the user wants the drone to ACT: \
take off, land, fly, turn, wait, aim the camera, come home, \
or wave. Fill "mission" with the actions; "target_en" is "".
- Camera aim uses gimbal_pitch (this aims the CAMERA, it does NOT move the \
drone): "look down"/"camera down" -> angle -60; "look up" -> angle 30; "look \
ahead"/"look forward" -> angle 0. Moving the drone up/down is fly_by with dz.
- "come back"/"go home"/"return to me" -> mission [{"type":"home"}].
- A greeting ("hello","hi","hey","how are you") -> mission [{"type":"wave"}].
- kind = "highlight" when the user wants a thing found, marked, followed, \
focused on or pointed at in the camera image. "target_en" = that thing as \
a short English noun phrase with its attributes (e.g. "red car", "person \
with the purple bag", "open window on the second floor"). "mission" is [].
- kind = "count" when the user asks how many of a thing are \
visible. "target_en" = the thing in English. "mission" is [].
- kind = "describe" when the user asks what is seen, asks about a place or \
direction in the image, or asks any other question about the camera view. \
"target_en" = the thing or region asked about, in English (e.g. "right side", \
"the building"), or "" for a general "what do you see". "mission" is [].
- kind = "reject" for a question about the drone itself (altitude, \
battery, flight time), a negation with no other order, or anything \
the actions cannot do. "target_en" is "". "mission" is [].
- Never put actions in "mission" for a kind other than \
"mission". An emphatic "do not" with no other order is "reject".
"""


def _unified(kind, target_en, mission):
    return json.dumps(
        {
            "kind": kind,
            "target_en": target_en,
            "mission": mission,
        },
        ensure_ascii=False
    )


UNIFIED_SHOTS = [
    (q, _unified("mission", "", json.loads(a))) for q, a in PLANNER_SHOTS_D
] + [
    # look down (camera)
    ("תסתכל למטה", _unified("mission", "", [{"type": "gimbal_pitch", "angle": -60}])),
    # aim camera up
    ("הפנה את המצלמה למעלה",
     _unified("mission", "", [{"type": "gimbal_pitch", "angle": 30}])),
    # come home
    ("חזור הביתה", _unified("mission", "", [{"type": "home"}])),
    # greeting -> wave
    ("שלום, מה שלומך", _unified("mission", "", [{"type": "wave"}])),
    ("סמן את המכונית האדומה", _unified("highlight", "red car", [])),
    ("עקוב אחרי האדם עם התיק הסגול",
     _unified("highlight", "person with the purple bag", [])),
    ("כמה אנשים עומדים ליד הכניסה", _unified("count", "people near the entrance", [])),
    ("תאר לי מה יש מימין", _unified("describe", "right side", [])),
    ("מה הגובה שלך עכשיו", _unified("reject", "", [])),
    ("בשום אופן אל תרד עכשיו", _unified("reject", "", [])),
    # live 2026-09-08: this double negation flew two spins once
    ("אל תפנה 90 מעלות שמאלה ואז אל תפנה ימינה", _unified("reject", "", [])),
]


# ======== PROMPTS.md: the owner-readable copy of the bench prompts ========

def write_prompts_md(path=None):
    """Write PROMPTS.md next to this file (not into the folder it is run from)."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROMPTS.md")
    shots = "\n".join(f"- user: `{u}`\n  assistant: `{a}`" for u, a in PLANNER_SHOTS_D)
    live_shots = "\n".join(
        f"- user: `{u}`\n  assistant: `{a}`" for u, a in UNIFIED_SHOTS
    )
    with open(path, "w") as f:
        f.write(f"""# The exact prompts the recognizer uses

Generated by `python3 prompts.py` from the \
constants in prompts.py -- edit there, not here.

## 1. App prompt

The system prompt the phone app ships today, \
reconstructed from SpeechResolving.kt:599-635.
Schema block in the app's short-JSON rendering, limited to the 5 whitelisted actions.

```
{APP_PROMPT}
```

## 2. Revised prompt (the planning scaffold)

Same scaffold plus a Signs & Directions section, \
a Refusals section, and 6 few-shot pairs sent
as user/assistant chat turns (not part of the system prompt text).

```
{REVISED_PROMPT}
```

The 6 example pairs:

{shots}

## 3. The live prompt (the app's one Gemma call)

The revised scaffold plus the routing rules: Hebrew in, `{{kind, target_en, mission}}`
out, under UNIFIED_GRAMMAR. Its example pairs are sent as chat turns.

```
{UNIFIED_PROMPT}
```

The example pairs:

{live_shots}
""")
    return


if __name__ == "__main__":
    write_prompts_md()
    print("PROMPTS.md regenerated")
