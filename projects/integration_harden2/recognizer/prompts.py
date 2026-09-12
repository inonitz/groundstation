import json
import re
"""Every prompt, grammar, and few-shot set the bench uses, in one place.
Run `python3 prompts.py` after editing to regenerate PROMPTS.md (the owner-readable copy).
APP_PROMPT = what the phone app ships today (reconstructed from SpeechResolving.kt:599-635,
5-action subset). REVISED_PROMPT = the candidate replacement (sign rule + refusal rule; its 6
few-shot pairs ride as chat turns, PLANNER_SHOTS_D). Planner calls carry WIRE_GRAMMAR (dx/dy/dz).
Translator calls: TRANSLATE_SYS + TRANSLATE_SHOTS + LINE_GRAMMAR for chat models; TranslateGemma
uses its native template TGEMMA_PROMPT on /completion (its jinja is unparseable by llama-server);
TGEMMA_REFINE is the measured-and-rejected draft-finalize experiment (round 6)."""

# ---- app prompt, reconstructed. Scaffold: SpeechResolving.kt:599-635. Schema block:
# ---- app's appendPropertyShortJson format (desc comment line, "name":  type, (optional) mark),
# ---- restricted to the 5 whitelisted actions.
SCHEMA_5 = '''"takeoff":  object {
\t"type": "takeoff",
},

"land":  object {
\t"type": "land",
},

// Moves aircraft relative to it's current position (m). At least one direction must be non zero.
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

Translate & Convert the user's natural language request into a JSON array of system actions.

Each action must exactly match one of the JSON Schemas below.

# Rules

- The JSON Schemas below are the ONLY valid actions.
- Never invent actions or fields. Never rephrase their names.
- Use ONLY the available system actions and fields below.
- Use the EXACT "type" value, field names & enum constants from the schemas.
- Output valid JSON Array only.

# Semantics

- Infer the user's intent and populate schema fields accordingly.
- If field is optional and the user did not explicitly or implicitly specify a value, you must omit the field.
- Comments in the input Schema provide each field's semantics. Don't output comments.
- Grammar in request like "x and y", "x then y", "do x, y" hints at multiple actions.
     -- for ex.: "takeoff, fly forward ... then fly upwards ... and then ..." is multiple actions.'''

APP_TAIL = '''# Output

Return ONLY the JSON array.'''

APP_PROMPT = APP_HEAD + "\n\n# Available Actions\n" + SCHEMA_5 + "\n\n" + APP_TAIL

# ---- revised prompt = app-prompt scaffold + the three measured deficits fixed:
# ---- (a) verbal->sign map (round-3: 7/14 top-arm fails were "turn right N" -> -N),
# ---- (b) negation/question -> [] rule, (c) few-shot (added separately as chat turns).
REVISED_PROMPT = APP_HEAD + '''

# Signs & Directions (follow EXACTLY)

- fly_by is in the aircraft body frame: dx+ forward, dx- backward; dy+ right, dy- left; dz+ up, dz- down.
- spin_by degrees: turning RIGHT = clockwise = POSITIVE degrees. Turning LEFT = counterclockwise = NEGATIVE degrees.
  "turn right 20 degrees" -> {"type":"spin_by","degrees":20}. "turn left 30 degrees" -> {"type":"spin_by","degrees":-30}.
- A full turn is 360 degrees. Half a turn is 180 degrees.
- Number words ("five", "half a meter") become digits (5, 0.5).

# Refusals

- A negated clause ("don't fly up", "do not land") produces NO action for that clause.
- Questions, status requests, and anything that is not a movement command -> output [] (empty array).
- Keep the actions in the exact order the user gave them.

# Available Actions
''' + SCHEMA_5 + "\n\n" + APP_TAIL

PLANNER_SHOTS_D = [
 ("fly left 12 meters", '[{"type":"fly_by","dy":-12}]'),
 ("go down 2 meters then fly forward 6 meters", '[{"type":"fly_by","dz":-2},{"type":"fly_by","dx":6}]'),
 ("do not fly up", "[]"),
 ("what's your altitude", "[]"),
 ("turn right 20 degrees", '[{"type":"spin_by","degrees":20}]'),
 ("take off, rise 4 meters, turn 90 degrees clockwise, fly forward 6 meters, and land",
  '[{"type":"takeoff"},{"type":"fly_by","dz":4},{"type":"spin_by","degrees":90},{"type":"fly_by","dx":6},{"type":"land"}]'),
]

WIRE_GRAMMAR = r'''
root ::= "[" ws (action (ws "," ws action)*)? ws "]"
action ::= takeoff | land | flyby | spinby | delay
takeoff ::= "{" ws "\"type\"" ws ":" ws "\"takeoff\"" ws "}"
land ::= "{" ws "\"type\"" ws ":" ws "\"land\"" ws "}"
flyby ::= "{" ws "\"type\"" ws ":" ws "\"fly_by\"" (ws "," ws axis)+ ws "}"
axis ::= ("\"dx\"" | "\"dy\"" | "\"dz\"" | "\"velocity\"") ws ":" ws num
spinby ::= "{" ws "\"type\"" ws ":" ws "\"spin_by\"" ws "," ws "\"degrees\"" ws ":" ws num ws "}"
delay ::= "{" ws "\"type\"" ws ":" ws "\"delay\"" ws "," ws "\"seconds\"" ws ":" ws num ws "}"
num ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
'''

TRANSLATE_SYS = ("You are a translation engine. Translate the user's Hebrew drone command to "
                 "English. Output ONLY the English translation, nothing else.")
TRANSLATE_SHOTS = [("טוס שמאלה שישה מטרים", "Fly left six meters"),
                   ("עצור במקום", "Stop in place")]
LINE_GRAMMAR = r'root ::= [^\n\r]+'

# V2 translator prompt (2026-09-08): six rules tied to Hy-MT2's measured failures (statement register,
# intent questions, numbers, rotation idioms, sideways = move, fillers) and two NEW few-shots (count
# kept at two, the campaign's measured optimum). Selected with bench.py --prompt v2 /
# run_list.py --prompt v2 / MVD_TRANSLATE_PROMPT=v2 in the live pipeline. V1 stays the default
# until the gate says otherwise. Design note: docs/active/2026-09-07-session-handoff.md section 11.4f.
TRANSLATE_SYS_V2 = (
 "You translate spoken Hebrew addressed to a camera drone into English for a flight planner. "
 "Output ONLY the English sentence.\n"
 "1. An instruction or a request becomes an English IMPERATIVE: \"take off\", \"climb 5 meters\". "
 "Never past tense, never \"it rose\", never \"it is possible to\". "
 "\"אפשר ל...\", \"תוכל ל...\", \"אתה יכול ל...\", \"בוא נ...\" are requests: translate them as imperatives.\n"
 "2. A question about the drone's intent or state stays a question and is never answered: "
 "\"האם אתה מתכוון/הולך/מתכנן ל...\", \"מה אתה רואה\", \"כמה ...\".\n"
 "3. Keep every number, unit and direction exactly. Write numbers as digits.\n"
 "4. Rotation words: \"עם כיוון השעון\" = clockwise, \"נגד כיוון השעון\" = counterclockwise, "
 "\"חצי סיבוב\" = a half turn, \"סיבוב שלם\" = a full turn, \"סיבוב וחצי\" = one and a half turns.\n"
 "5. Sideways motion is \"move right/left N meters\", never \"turn\". \"פנה\"/\"הסתובב\" are \"turn\".\n"
 "6. Fillers are not actions: \"רגע\", \"שנייה\", \"תקשיב\", \"יאללה\", \"בסדר\", \"יופי\" are dropped or "
 "become \"then\". Keep the order and the number of actions, one clause per action.")
TRANSLATE_SHOTS_V2 = [
 ("אפשר להמריא ואז לעלות חמישה מטרים?", "Take off, then climb 5 meters."),
 ("תקשיב, קודם טוס אחורה ארבעה מטרים, שנייה אחרי זה זוז שמאלה שלושה מטרים ובסוף הסתובב תשעים מעלות עם כיוון השעון",
  "First fly backward 4 meters, then move left 3 meters, and finally turn 90 degrees clockwise."),
]
TRANSLATE_PROMPTS = {"v1": (TRANSLATE_SYS, TRANSLATE_SHOTS), "v2": (TRANSLATE_SYS_V2, TRANSLATE_SHOTS_V2)}

# Purpose-objective translate prompt (owner idea 2026-09-02): tell the translator WHAT THE
# TRANSLATION IS FOR instead of asking for faithful translation. Measured against TRANSLATE_SYS
# by bench.py --pipeline.
TRANSLATE_SYS_PURPOSE = (
 "You are the language front-end of a voice-controlled camera drone. The user speaks Hebrew. "
 "Rewrite the utterance as clear imperative English drone commands for the flight planner. "
 "Rules: one short imperative clause per action, keep the user's order and the exact count of "
 "actions; preserve every number, unit and direction exactly; verbs: take off, land, climb, "
 "descend, fly, move, turn, rotate, wait. "
 "Do not narrate, no introductions, do not add or drop actions; questions and negated requests "
 "stay questions/negations. Output ONLY the English rewrite.")
PURPOSE_SHOTS = [
 ("טוס שמאלה שישה מטרים", "Move left six meters"),
 ("תמריא, חכה שלוש שניות ואז תנחת", "Take off, wait three seconds, then land"),
 ("תעלה שני מטרים ואז פנה ימינה תשעים מעלות ותנחת",
  "Climb two meters, then turn right ninety degrees, then land"),
 ("אל תסתובב בבקשה", "Please do not rotate"),
]

# Hebrew sign addendum: appended to REVISED_PROMPT ONLY in the direct-Hebrew lane (the main
# English arms stay untouched). Round-2026-09-02 finding: without it DictaLM maps the Hebrew
# clockwise idiom to NEGATIVE degrees.
HE_SIGN_ADDENDUM = """

# Hebrew signs
- "עם כיוון השעון" = clockwise = POSITIVE degrees. "נגד כיוון השעון" = counterclockwise = NEGATIVE degrees.
- "ימינה" = right = dy positive (or positive degrees for turns). "שמאלה" = left = dy negative (or negative degrees)."""

# Hebrew twins of PLANNER_SHOTS_D, for direct-Hebrew planning (no translation stage).
PLANNER_SHOTS_D_HE = [
 ("טוס שמאלה שנים עשר מטרים", '[{"type":"fly_by","dy":-12}]'),
 ("רד שני מטרים ואז טוס קדימה שישה מטרים", '[{"type":"fly_by","dz":-2},{"type":"fly_by","dx":6}]'),
 ("אל תטוס למעלה", "[]"),
 ("מה הגובה שלך", "[]"),
 ("פנה ימינה עשרים מעלות", '[{"type":"spin_by","degrees":20}]'),
 ("הסתובב שישים מעלות עם כיוון השעון", '[{"type":"spin_by","degrees":60}]'),
 ("המראה, עלה ארבעה מטרים, הסתובב תשעים מעלות עם כיוון השעון, טוס קדימה שישה מטרים ונחת",
  '[{"type":"takeoff"},{"type":"fly_by","dz":4},{"type":"spin_by","degrees":90},{"type":"fly_by","dx":6},{"type":"land"}]'),
]

TGEMMA_PROMPT = ("<start_of_turn>user\n"
 "You are a professional Hebrew (he) to English (en) translator. Your goal is to accurately convey "
 "the meaning and nuances of the original Hebrew text while adhering to English grammar, "
 "vocabulary, and cultural sensitivities.\n"
 "Produce only the English translation, without any additional explanations or commentary. "
 "Please translate the following Hebrew text into English:\n\n\n"
 "{he}<end_of_turn>\n<start_of_turn>model\n")

TGEMMA_REFINE = ("<start_of_turn>user\n"
 "You are a professional Hebrew (he) to English (en) translator.\n"
 "The Hebrew text below is the ground truth. The draft English translation below it was produced "
 "by another system and may contain errors or omissions. Correct and finalize the translation "
 "against the Hebrew ground truth. Produce only the final English translation, without any "
 "additional explanations or commentary.\n\n"
 "Hebrew ground truth:\n{he}\n\n"
 "Draft translation:\n{draft}<end_of_turn>\n<start_of_turn>model\n")

def write_prompts_md(path="PROMPTS.md"):
    shots = "\n".join(f"- user: `{u}`\n  assistant: `{a}`" for u, a in PLANNER_SHOTS_D)
    tshots = "\n".join(f"- user: `{u}`\n  assistant: `{a}`" for u, a in TRANSLATE_SHOTS)
    open(path, "w").write(f"""# The exact prompts the bench uses

Generated by `python3 prompts.py` from the constants in prompts.py -- edit there, not here.

## 1. App prompt

The system prompt the phone app ships today, reconstructed from SpeechResolving.kt:599-635.
Schema block in the app's short-JSON rendering, limited to the 5 whitelisted actions.

```
{APP_PROMPT}
```

## 2. Revised prompt (the candidate replacement)

Same scaffold plus: a Signs & Directions section, a Refusals section, and 6 few-shot pairs sent
as user/assistant chat turns (not part of the system prompt text).

```
{REVISED_PROMPT}
```

The 6 example pairs:

{shots}

## 3. Translate-stage prompts

Chat translators (DictaLM; Qwen3-VL in its translator arm) get this system prompt, 2 example
pairs, and a one-line GBNF grammar:

```
{TRANSLATE_SYS}
```

{tshots}

TranslateGemma runs its native template on the raw completion endpoint:

```
{TGEMMA_PROMPT.format(he="<the Hebrew sentence>")}
```

The refine experiment (round 6, measured worse than TranslateGemma alone -- kept for the record):

```
{TGEMMA_REFINE.format(he="<the Hebrew sentence>", draft="<DictaLM draft>")}
```
""")

if __name__ == "__main__":
    write_prompts_md()
    print("PROMPTS.md regenerated")


# TranslateGemma's own instruction as a chat system prompt, ZERO-shot, for the "after" arm of the Gemma 4 translator
# measurement (owner ask 2026-09-08). Same words as TGEMMA_PROMPT; the server applies the model's chat template.
TGEMMA_SYS = re.split(r"\n+\{he\}", TGEMMA_PROMPT.split("<start_of_turn>user\n", 1)[1], 1)[0].strip()
TRANSLATE_PROMPTS["tgemma"] = (TGEMMA_SYS, ())


# ============ harden2 (2026-09-08): ONE Gemma call routes, plans and names the object for SAM3 ============
# The model reads the Hebrew directly (no translator). kind = mission | highlight | count | describe | reject.
# target_en = the object phrase in English for the segmenter (SAM3 reads English only); "" when not needed.
# mission = the wire mission (same schema as WIRE_GRAMMAR); [] unless kind == "mission".
UNIFIED_GRAMMAR = r"""
root ::= "{" ws "\"kind\"" ws ":" ws kind ws "," ws "\"target_en\"" ws ":" ws "\"" str "\"" ws "," ws "\"mission\"" ws ":" ws missionarr ws "}"
kind ::= "\"mission\"" | "\"highlight\"" | "\"count\"" | "\"describe\"" | "\"reject\""
str ::= [^"\n\\]*
missionarr ::= "[" ws (action (ws "," ws action)*)? ws "]"
action ::= takeoff | land | flyby | spinby | delay
takeoff ::= "{" ws "\"type\"" ws ":" ws "\"takeoff\"" ws "}"
land ::= "{" ws "\"type\"" ws ":" ws "\"land\"" ws "}"
flyby ::= "{" ws "\"type\"" ws ":" ws "\"fly_by\"" (ws "," ws axis)+ ws "}"
axis ::= ("\"dx\"" | "\"dy\"" | "\"dz\"" | "\"velocity\"") ws ":" ws num
spinby ::= "{" ws "\"type\"" ws ":" ws "\"spin_by\"" ws "," ws "\"degrees\"" ws ":" ws num ws "}"
delay ::= "{" ws "\"type\"" ws ":" ws "\"delay\"" ws "," ws "\"seconds\"" ws ":" ws num ws "}"
num ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
"""

UNIFIED_PROMPT = REVISED_PROMPT + """

# Input language and routing (harden2)

- The request is in Hebrew (sometimes with an English word inside). Understand it directly.
- Output ONE JSON object: {"kind": ..., "target_en": ..., "mission": [...]}.
- kind = "mission" when the user wants the drone to MOVE (take off, land, fly, turn, wait). Fill "mission" with the actions; "target_en" is "".
- kind = "highlight" when the user wants a thing found, marked, followed, focused on or pointed at in the camera image. "target_en" = that thing as a short English noun phrase with its attributes (e.g. "red car", "person with the purple bag", "open window on the second floor"). "mission" is [].
- kind = "count" when the user asks how many of a thing are visible. "target_en" = the thing in English. "mission" is [].
- kind = "describe" when the user asks what is seen, asks about a place or direction in the image, or asks any other question about the camera view. "target_en" = the thing or region asked about, in English (e.g. "right side", "the building"), or "" for a general "what do you see". "mission" is [].
- kind = "reject" for a question about the drone itself (altitude, battery, flight time), a negation with no other order, a greeting, or anything the actions cannot do. "target_en" is "". "mission" is [].
- Never put actions in "mission" for a kind other than "mission". An emphatic "do not" with no other order is "reject".
"""

def _unified(kind, target_en, mission):
    return json.dumps({"kind": kind, "target_en": target_en, "mission": mission}, ensure_ascii=False)

UNIFIED_SHOTS = [(q, _unified("mission", "", json.loads(a))) for q, a in PLANNER_SHOTS_D] + [
    ("סמן את המכונית האדומה", _unified("highlight", "red car", [])),
    ("עקוב אחרי האדם עם התיק הסגול", _unified("highlight", "person with the purple bag", [])),
    ("כמה אנשים עומדים ליד הכניסה", _unified("count", "people near the entrance", [])),
    ("תאר לי מה יש מימין", _unified("describe", "right side", [])),
    ("מה הגובה שלך עכשיו", _unified("reject", "", [])),
    ("בשום אופן אל תרד עכשיו", _unified("reject", "", [])),
    ("אל תפנה 90 מעלות שמאלה ואז אל תפנה ימינה", _unified("reject", "", [])),   # live 2026-09-08: this double negation flew two spins once
]
