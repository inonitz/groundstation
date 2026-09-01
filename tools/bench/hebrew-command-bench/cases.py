"""32 paired HE/EN command cases + the planner scorer. Shared by every pipeline so all rows
are scored identically. Expected: list of (type, key, value) per step; value None = any;
expected None = open-ended (scored for whitelist validity only)."""
SYSTEM = """You are a drone mission planner. Convert the user's command into a JSON array of actions.
Allowed action types ONLY:
  {"type":"takeoff"} {"type":"land"}
  {"type":"fly_by","x":M,"y":M,"z":M}   (meters; x=forward,-x=back; y=right; z=up,-z=down; omit zero axes)
  {"type":"spin_by","degrees":D}        (positive=clockwise, negative=counterclockwise)
  {"type":"delay","seconds":S}
Rules: output ONLY the JSON array, no prose, no markdown. Keep the order the user gave.
If the command is not a movement command, output []."""

CASES = [
 # --- originals (12) ---
 ("up10",       "עלה עשרה מטרים",                        "go up 10 meters",                  [("fly_by","z",10)]),
 ("fwd5",       "טוס קדימה חמישה מטרים",                 "fly forward 5 meters",             [("fly_by","x",5)]),
 ("spin90cw",   "הסתובב תשעים מעלות עם כיוון השעון",      "rotate 90 degrees clockwise",      [("spin_by","degrees",90)]),
 ("takeoff",    "המראה",                                   "take off",                         [("takeoff",None,None)]),
 ("land",       "נחת",                                     "land",                             [("land",None,None)]),
 ("combo3",     "עלה עשרה מטרים, הסתובב תשעים מעלות עם כיוון השעון ואז טוס קדימה חמישה מטרים",
                "go up 10 meters, rotate 90 degrees clockwise, then fly forward 5 meters",
                [("fly_by","z",10),("spin_by","degrees",90),("fly_by","x",5)]),
 ("combo_tl",   "המראה, עלה חמישה מטרים, המתן שלוש שניות ונחת",
                "take off, go up 5 meters, wait 3 seconds, and land",
                [("takeoff",None,None),("fly_by","z",5),("delay","seconds",3),("land",None,None)]),
 ("back2left3", "טוס אחורה שני מטרים ואז שמאלה שלושה מטרים", "fly backward 2 meters then left 3 meters",
                [("fly_by","x",-2),("fly_by","y",-3)]),
 ("ccw45",      "הסתובב ארבעים וחמש מעלות נגד כיוון השעון", "rotate 45 degrees counterclockwise",
                [("spin_by","degrees",-45)]),
 ("down3",      "רד שלושה מטרים",                          "go down 3 meters",                 [("fly_by","z",-3)]),
 ("question",   "מה אתה רואה עכשיו?",                      "what do you see right now?",       []),
 ("square",     "טוס בריבוע של שני מטרים",                 "fly in a square of 2 meters",      None),
 # --- new (20) ---
 ("up2",        "עלה שני מטרים",                           "go up 2 meters",                   [("fly_by","z",2)]),
 ("right4",     "טוס ימינה ארבעה מטרים",                   "fly right 4 meters",               [("fly_by","y",4)]),
 ("left7",      "זוז שמאלה שבעה מטרים",                    "move left 7 meters",               [("fly_by","y",-7)]),
 ("back10",     "טוס אחורה עשרה מטרים",                    "fly backward 10 meters",           [("fly_by","x",-10)]),
 ("fwd15",      "התקדם חמישה עשר מטרים",                   "advance 15 meters",                [("fly_by","x",15)]),
 ("spin180cw",  "הסתובב מאה שמונים מעלות עם כיוון השעון",   "rotate 180 degrees clockwise",     [("spin_by","degrees",180)]),
 ("spin360",    "עשה סיבוב שלם עם כיוון השעון",            "do a full turn clockwise",         [("spin_by","degrees",360)]),
 ("wait5",      "חכה חמש שניות",                           "wait 5 seconds",                   [("delay","seconds",5)]),
 ("up_half",    "עלה חצי מטר",                             "go up half a meter",               [("fly_by","z",0.5)]),
 ("combo2b",    "המראה ואז עלה שלושה מטרים",               "take off then go up 3 meters",
                [("takeoff",None,None),("fly_by","z",3)]),
 ("combo4",     "טוס קדימה ארבעה מטרים, ימינה שני מטרים, אחורה ארבעה מטרים ואז שמאלה שני מטרים",
                "fly forward 4 meters, right 2 meters, backward 4 meters, then left 2 meters",
                [("fly_by","x",4),("fly_by","y",2),("fly_by","x",-4),("fly_by","y",-2)]),
 ("combo5",     "המראה, עלה שני מטרים, הסתובב תשעים מעלות עם כיוון השעון, טוס קדימה שלושה מטרים ונחת",
                "take off, go up 2 meters, rotate 90 degrees clockwise, fly forward 3 meters, and land",
                [("takeoff",None,None),("fly_by","z",2),("spin_by","degrees",90),("fly_by","x",3),("land",None,None)]),
 ("digit12",    "עלה 12 מטרים",                            "go up 12 meters",                  [("fly_by","z",12)]),
 ("digit45deg", "פנה ימינה 45 מעלות",                      "turn right 45 degrees",            [("spin_by","degrees",45)]),
 ("question2",  "כמה אנשים אתה רואה",                      "how many people do you see",       []),
 ("q_land_trap","האם אתה מתכוון לנחות בקרוב",              "are you going to land soon",       []),
 ("neg_trap",   "אל תטוס קדימה",                           "don't fly forward",                []),
 ("colloq_up",  "תעלה עשרה מטרים",                         "climb 10 meters",                  [("fly_by","z",10)]),
 ("land_now",   "נחת עכשיו",                               "land now",                         [("land",None,None)]),
 ("takeoff_ctx","בצע המראה",                               "perform takeoff",                  [("takeoff",None,None)]),
]

from cases_generated import GENERATED_CASES
from cases_realistic import REALISTIC_CASES
CASES = CASES + GENERATED_CASES + REALISTIC_CASES

ALLOWED = {"takeoff": set(), "land": set(), "fly_by": {"x","y","z"},
           "spin_by": {"degrees"}, "delay": {"seconds"}}

import json, re

def parse(out):
    m = re.search(r"\[.*\]", out or "", re.S)
    if not m: return None
    try: arr = json.loads(m.group(0))
    except Exception: return None
    if not isinstance(arr, list): return None
    for a in arr:
        if not isinstance(a, dict) or a.get("type") not in ALLOWED: return None
        for k in a:
            if k != "type" and k not in ALLOWED[a["type"]]: return None
    return arr

def score(arr, expected):
    if arr is None: return "invalid"
    if expected is None: return "valid(open)"
    if len(arr) != len(expected): return f"wrong-len({len(arr)}vs{len(expected)})"
    for a, (t, k, v) in zip(arr, expected):
        if a["type"] != t: return f"wrong-verb({a['type']}vs{t})"
        if k is not None:
            got = a.get(k)
            if got is None: return f"missing-{k}"
            if v is None: continue
            g = float(got)
            if v == "+":
                if g <= 0: return f"wrong-sign-{k}({got})"
            elif v == "-":
                if g >= 0: return f"wrong-sign-{k}({got})"
            elif isinstance(v, tuple) and v[0] == "abs":
                if abs(abs(g) - v[1]) > 0.01: return f"wrong-abs-{k}({got}vs{v[1]})"
            elif abs(g - float(v)) > 0.01: return f"wrong-{k}({got}vs{v})"
    return "CORRECT"
