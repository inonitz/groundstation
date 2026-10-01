# recognizer: the agent doc

## Brief (the main agent, 2026-09-28; do not edit)
Name: recognizer. ROS_DOMAIN_ID=11. The shared rules: docs/refactor/README.md.

**Context.** The recognizer turns a transcript into an action: a mission for the phone app, a
perception request, or a spoken answer. Today recognizer/recognizer.py decides and acts in one
step. Two benchmarks copied its routing: bench/hebrew-command-bench/unified_bench.py and
bench/whole-system/run_list.py. On 2026-09-26 the copy showed the guards as inert, and its scorer
failed two lines on "+90" (HISTORY: "run_list on real Gemma").

**Objective.** One decide function that the app and the benchmark both call. One benchmark of the
recognizer: "a benchmark of the recognizer as a function of the backend" (owner). Then correct
number reading, with all seven front letters and the fractions.

**Tasks, in order.** The full text is in handoff 9d.
1. A1: route() decides and sends nothing; handle() = route() + act.
   - Rulings: ledger 1.8 ("separate functions that are chained together. One should make the
     decision, one should do the acting") and D3.
   - The app keeps its behavior: the tests in test/test_recognizer.py pass unchanged.
   - Add a test that route() sends nothing, with a mutation check.
   - Sync docs/api-harden2/recognizer.h and recognizer/README.md.
2. B1: bench/recognizer/accuracy.py.
   - Rulings: Q1, R1, R2, M2, T2, U2, U2.2, U2.3, V3, W1, X1, X3, and the Benchmarks part of the
     spec section "Owner rulings 2026-09-27 and 2026-09-28".
   - The cases: bench/hebrew-command-bench/cases_commands.py, cases_perception.py (the verbose set
     is generated once), and the lists in datasets/e2e/ become JSON files in datasets/recognizer/,
     as they are. V3: no review of the expected values.
   - Path A: a JSON sentence file -> route() -> the scorer. A file argument runs one file.
   - Path B comes later (bench, task B2): WAV + expected -> whisper -> path A. Leave room for it;
     do not build it.
   - One scorer, in bench/recognizer/, not in log/. It grades the steps, reject, emergency, and for
     perception the kind and the target words (X1). It must read "+90" without "deg".
   - It calls route(), never a copy of the routing.
   - Write bench/recognizer/README.md: why it exists, how to run it from start to finish, results.
   - Verify it on real Gemma (lock gpu). Compare with the 2026-09-26 run in HISTORY (30 / 2 / 18).
   - Then delete bench/hebrew-command-bench/unified_bench.py, bench/whole-system/run_list.py (bench
     leaves it to you), log/score.py, and `run.sh score` with its lines in
     docs/spec-harden2-run-arguments.md and in the tests.
   - As soon as the JSON format is fixed, write it in the section "B1 JSON format" below. bench
     needs it for B3 and B2.
3. A2: the numbers.
   - Build a sentence set with fractions and all seven front letters. Measure Gemma and the guard
     on it first (lock gpu). Then complete the tables in recognizer/numbers.py and util/hebrew.py.
   - Rulings: C.3 (the owner's fraction examples), Q8 ("ALL SEVEN! THIS WONT ARISE JUST WITH
     VAV!"), D11, R8, T5. HISTORY "the number guard misreads" has the measured examples.
   - The fractions include a quarter, a third and an eighth.
   - The seven front letters:

| letter | meaning |
|---|---|
| ו | and |
| ה | the |
| ב | in |
| ל | to |
| מ | from |
| כ | about |
| ש | that |

**Yours (no lock):** recognizer/, test/test_recognizer.py, util/hebrew.py, bench/recognizer/ (the
confirm tool there is bench's), datasets/recognizer/, docs/api-harden2/recognizer.h,
bench/hebrew-command-bench/unified_bench.py, bench/whole-system/run_list.py, log/score.py.

**Shared (lock the path):** run.sh, docs/spec-harden2-run-arguments.md, bench/README.md,
bench/recognizer/README.md (once bench adds the confirm tool), test/README.md, test/test_log.py,
log/__init__.py, projects/integration_harden2/README.md.

**Do not touch:** app/main.py; bench/whole-system/ other than run_list.py; the other files in
bench/hebrew-command-bench/ (bench and investigator retire them).

**Resources:** gpu (B1 verification, A2 measurement), suite.

## B1 JSON format (for bench)
Fixed 2026-09-28 by recognizer. One file per set in /root/groundstation/datasets/recognizer/
(commands.json, verbose.json, emergency.json, perception.json, military.json, and one per list of
datasets/e2e: live-test-50.json, live-test-75.json, live-test-e2e-50.json, live-test-subset.json).

```json
{
  "set": "commands",
  "source": "bench/hebrew-command-bench/cases_commands.py CASES (converted 2026-09-28)",
  "cases": [
    {"name": "up10", "he": "עלה עשרה מטרים", "en": "go up 10 meters",
     "expect": {"kind": "mission", "steps": [["fly_by", "dz", 10]]}},
    {"name": "question", "he": "מה אתה רואה עכשיו?", "expect": {"kind": "none"}}
  ]
}
```

A case:
- `name` (unique in its file), `he` (the sentence route() gets), `expect` (below): required.
- `en` (the English reference), `note` (the source list's expected text), `depth`, `class`,
  `file`, `case`: optional, kept from the source.
- Path B (bench, B2/B3): a recordings file uses the same case, plus `"wav"`: the clip's path
  relative to /root/groundstation (for example "datasets/asr/clips/<name>.wav"). Its `he` is the
  CONFIRMED sentence (whisper's text is compared with it for the word error rate).

`expect.kind`:
- `mission` + `steps`: the mission must be exactly these steps, in order. A step is
  `[type, key, value]`, in the phone app's names (fly_by: dx / dy / dz in metres; spin_by:
  degrees; delay: seconds). `key` null = no value checked (takeoff, land). `value`: a number,
  null (any value), "+" or "-" (the sign only), or ["abs", n] (the magnitude only).
- `open`: any mission that flies passes (the old `expected None`).
- `none`: nothing may fly: a reject, an empty plan, a perception request, or a halt passes.
- `emergency`: the fast path must halt (route() kind "emergency").
- `perception` + `groups`: the kind must be highlight, count or describe, and each keyword group
  (a list of synonyms) needs one synonym inside "<kind words> the <target>". `groups` [] = the
  kind alone.
- `review`: not graded (the source list gives no single expected result); `note` says why.

The scorer is bench/recognizer/scorer.py: `score(expect, decision) -> (verdict, reason)`, verdict
PASS | FAIL | REVIEW. `read_notation(text) -> expect` turns the live-list notation ("dz+10, +90
deg, takeoff, delay 3, EMPTY, halt, VLM ...") into an `expect`; a correction typed in that notation
can go through it.

## Brief 2: J5, then the J1 + J4 drafts, then TR1, TR3, TR5 (the main agent, 2026-09-29; do not edit)
Rulings (ledger): J2 (2), J5 (2), J1 (3), J4 (3), TR1, TR3, TR5, V1 (the JSON in datasets/ is public; audio never
in git). Rules for this brief: docs/refactor/README.md holds. A module's tests are written WITH it (guidelines, 2026-09-28). Never delete working code because git keeps it (TR16). No git command at all. Never upgrade or reinstall torch, transformers or bitsandbytes in the main environment: anything that needs other versions goes into its own venv, created by a script. Lock gpu for every GPU run; one GPU job at a time. Control stays the mock.
1. J5, one home per sentence (the owner: "merge and remove duplicates ... putting them all in their respective
   places by category"). Today: 6 topical files (528 cases, 526 distinct) and 4 live lists (201 cases; 186 are
   copies; 15 exist only in live-test-50); 4 unnumbered lines of datasets/e2e/live-test-50.md were never
   copied. Do: every sentence once, in the topical file of its kind; the 15 + 4 go there too (about 545
   sentences); each live list becomes an ordered list of case names (no copied sentence); where copies
   disagree, an exact expected result beats "review"/"open", and the topical file's keyword groups win (list
   those 21 in your doc for the owner); the notation reader learns "either way" (-> ["abs", n]) and the turn
   case keeps it; accuracy.py counts each sentence once, runs a live list by name, and prints one in order
   (--print NAME, Hebrew through python-bidi get_display, as bench/recognizer/confirm.py does); then delete
   datasets/e2e/*.md (rm; if refused, "For the owner"). Update bench/recognizer/README.md and confirm.py if its
   case pool changes. Re-run accuracy.py (lock gpu) and report the new totals.
2. J1: for each of the 21 military sentences, draft its expected decision (a mission with steps, a vision
   request, or a reject); J4: for each of the 15 "open" cases in commands.json, draft its accepted step lists
   (1-3 each; the scorer passes a plan that matches any; kind "mission" with "alternatives"). Mark every draft
   "draft": true. Put a review table in your doc for the owner: the Hebrew in its own cell, the English gloss,
   the proposed decision. The owner confirms before a draft counts.
3. Tests: TR1 (the bypass "wait N seconds" and "a full turn"), TR3 (a plan equal to a few-shot example is refused
   at routing level and nothing flies), TR5 (an empty plan; a non-JSON reply).
Then stop with "WAITING".

## Brief 3: SC1, the scorer checks the vision kind (the main agent, 2026-09-30; do not edit)
Ruling (ledger SC1 (2) "Option A"): the scorer grades a vision request's kind (highlight, count, describe) from its own
field, not through keyword groups. Draft the expected kind for each of the 138 perception cases (and the military and
recording cases where it applies), marked draft for the owner's joint review; the scorer ignores drafts. Keep the
labelling page's format readable (tools/asr-verify-transcript saves the kind as the first keyword group today: agree
the new field with its labels.py; lock it). Tests with it. Re-run accuracy.py only after the owner's review.

## Notes
- A1: recognizer/recognizer.py has `route(text) -> Decision` (decides, sends nothing), `act(decision)
  -> Routed`, `handle(text)` = both. The benchmark calls `route()` on a Recognizer built with
  control=None, vision=None: any send would crash, so nothing can be sent.
- B1: bench/recognizer/accuracy.py (path A) + scorer.py (the one scorer, with read_notation) +
  README.md. The cases: datasets/recognizer/*.json (format: section "B1 JSON format" above). The
  conversion ran once from a scratch script (not kept: V3 "as they are"; the Python case files
  are retired by B7). J5 (2026-09-29): the live lists are now name lists in datasets/recognizer/; datasets/e2e/*.md wait on the owner's rm.
- B1: accuracy.py starts Gemma itself (supervisor + gemma.server.process, port 18091); it no longer
  needs bench/hebrew-command-bench/bench.py, so B7 may delete bench.py.
- B1: the bonus lines of live-test-50.md (unnumbered) are not converted; run_list never read them.
- A2: util/hebrew.py holds the tables (FRONT_LETTERS, UNIT_WORDS, FRACTIONS, FRACTION_PLURALS,
  split_front); recognizer/numbers.py reads the fractions (read_fractions) and the prefixed
  numbers; guards.numbers_vs_mission matches within 0.01. hebnum_to_digits now keeps a front
  letter as "ב-5" and no longer composes two units in a row (אחד וחמישה was read as 5).
- util/mission.py: after log/score.py goes, only app/turns.py uses step_text. The rule "a helper
  used by one module lives in it" says it moves into app/. Not done: app/ is perf's area now.

### Review for the owner: J1, the 21 military sentences (drafts; the scorer ignores them until confirmed)
Each draft is the case's `draft` field in datasets/recognizer/military.json, marked "draft": true.
Confirming one moves it to `expect`. A reject passes a vision request too (the rule of "none").

| case | Hebrew | English gloss | proposed decision |
|---|---|---|---|
| s_indian_circle | תבצע מעגל אינדיאני על המטרה מולך | Perform an Indian circle around the target in front of you | reject (nothing flies) |
| s_sitrep | טפס לגובה ותן לי תמונת מצב | Climb to altitude and give me a situation picture | reject (nothing flies) |
| s_jump_point | קפוץ לנקודה ותשאר עליה | Jump to the point and stay on it | reject (nothing flies) |
| s_gentle_scan | תעשה לי סריקה עדינה על הגזרה | Do a gentle scan over the sector | vision request (the kind alone) |
| s_eye_junction | שים עין על הצומת ואל תרד ממנו | Keep an eye on the junction and do not come off it | vision request: junction/intersection |
| s_zoom_suspect | תן זום על הרכב החשוד ותחזיק אותו במרכז | Zoom in on the suspicious vehicle and hold it in the center | vision request: vehicle/car + suspicious |
| s_route_escort | עלה על ציר התנועה ותלווה אותו עד הפנייה | Get on the movement route and follow it until the turn | reject (nothing flies) |
| s_dead_ground | תפוס גובה, יש לך שטח מת מאחורי הגבעה | Gain altitude, you have dead ground behind the hill | reject (nothing flies) |
| s_give_distance | רחפן שני נכנס לגזרה שלך, תן לו מרחק | A second drone is entering your sector, give it distance | reject (nothing flies) |
| s_one_more_pass | תעשה עוד סיבוב מעל השכונה ואז תחזור הביתה | Do one more pass over the neighborhood and then come back home | reject (nothing flies) |
| s_grid_out | עבור לנ.צ. שנתתי לך, סוף | Proceed to the grid reference I gave you, out | reject (nothing flies) |
| s_roger_over | רות, ממשיך בסריקה, עבור | Roger, continuing the scan, over | reject (nothing flies) |
| s_cp_visual | יש לי קשר עין עם החפ"ק ליד המבנה | I have eye contact with the command post near the structure | reject (nothing flies) |
| s_eyes_on | תדווח כשיש לך עיניים על המטרה | Report when you have eyes on the target | vision request: target |
| s_rally_point | קיבלתי, חוזר לנק' האיסוף | Roger, returning to the collection point | reject (nothing flies) |
| s_feet_hold | תעלה לשמונה מאות רגל ותחכה בהמתנה מעל האזור | Climb to eight hundred feet and hold over the area | reject (nothing flies) |
| s_lost_uav | אבד קשר עם הכטב"ם, תתחיל סריקה בגזרה הצפונית | Contact with the UAV was lost, start scanning in the northern sector | reject (nothing flies) |
| s_scramble | המראה מיידית, יש הקפצה | Immediate takeoff, there is a scramble | mission, any of: [takeoff] |
| s_obs_report | החזק תצפית על הבית הלבן, דווח כל תזוזה, עבור | Maintain observation on the white house, report any movement, over | vision request: house/home/building + white |
| s_wadi_route | טוס נמוך על הוואדי עד המפגש עם הציר, שם תמתין | Fly low along the wadi until it meets the route, and wait there | reject (nothing flies) |
| s75_observe_junction | תן לי תצפית על הצומת ודווח | Give me an observation of the junction and report | vision request: junction/intersection |

### Review for the owner: J4, the open cases (drafts)
Each draft is the case's `draft` field in datasets/recognizer/commands.json. The scorer already
reads `alternatives` (a plan passes when it matches any one list) and "a halt" (owner J4 rule 2).
Two of the 15 are no longer "open": J5's rule (an exact result beats "open") gave square and r_dis4
the live list's "must NOT fly". Their drafts propose a flying answer instead; the owner picks.

| case | Hebrew | English gloss | today | proposed decision |
|---|---|---|---|---|
| square | טוס בריבוע של שני מטרים | fly in a square of 2 meters | none | mission, any of: [fly_by dx 2, fly_by dy 2, fly_by dx -2, fly_by dy -2] OR [fly_by dx 2, fly_by dy -2, fly_by dx -2, fly_by dy 2] |
| r_around | תסתובב אליי | turn around toward me | open | mission, any of: [spin_by degrees ['abs', 180]] |
| r_dis1 | טוס קדימה חמישה מטרים ותצלם את הבית | fly forward 5 meters and photograph the house | open | mission, any of: [fly_by dx 5] |
| r_dis2 | תעלה שלושה מטרים ותסתכל מסביב | go up 3 meters and look around | open | mission, any of: [fly_by dz 3] OR [fly_by dz 3, spin_by degrees ['abs', 360]] |
| r_dis3 | תמריא ותחפש את המכונית | take off and search for the car | open | mission, any of: [takeoff] |
| r_dis4 | טוס ימינה שני מטרים ותגיד לי מה אתה רואה | fly right 2 meters and tell me what you see | none | mission, any of: [fly_by dy 2] |
| l75_hover_stand | תעמוד במקום | hold position | open | mission, any of: [a halt] OR [delay seconds] |
| l75_return_home | חזור אליי | come back to me | open | mission, any of: [home] |
| l75_stay_put | תישאר במקום | stay in place | open | mission, any of: [a halt] OR [delay seconds] |
| l75_bit_forward | קצת יותר קדימה | a bit more forward | open | mission, any of: [fly_by dx +] |
| l75_higher | יותר גבוה | higher | open | mission, any of: [fly_by dz +] |
| l75_do_hover | תעשה hover | do a hover | open | mission, any of: [a halt] OR [delay seconds] |
| l75_ten_feet | עלה עשרה פיט | go up 10 feet | open | mission, any of: [fly_by dz 3] OR [fly_by dz 3.05] |
| l75_gimbal_down | סובב את המצלמה למטה | point the camera down | open | mission, any of: [gimbal_pitch angle -] |
| l75_toward_white_bldg | טוס לכיוון הבניין הלבן | fly toward the white building | open | reject (nothing flies) |

### Review for the owner: SC1, the expected vision kind (drafts; the scorer ignores them until confirmed)
The scorer now fails a vision request of another kind when a case names its kind in the field
`vision`. Each draft below is the case's `draft` field (the case's expect plus `vision`,
marked "draft": true); confirming one moves it to `expect`. Drafted from the English reference:
count for "count / how many", describe for questions ("what", "is there", "identify", "look"),
highlight for the rest. Worth a look: lp_look_down and p75_look_right (a look direction, drafted
describe; they may be a gimbal move), and the "is there ..." questions (drafted describe; count
is the other reading).

Count (12) and describe (22):

| case | Hebrew | English gloss | proposed kind |
|---|---|---|---|
| i_top_windows | ספור את החלונות בקומה העליונה של המגדל | Count the windows on the top floor of the tower | count |
| i_cars_by_flag | ספור את המכוניות שחונות מול הבניין עם הדגל | Count the cars parked in front of the building with the flag | count |
| i_bench_fountain | ספור את האנשים שיושבים על הספסלים משמאל למזרקה | Count the people sitting on the benches to the left of the fountain | count |
| i_main_steps | ספור את המדרגות בכניסה הראשית של הבניין הגבוה | Count the steps at the main entrance of the tall building | count |
| i_boats_pier | ספור את הסירות הקשורות למזח הצפוני | Count the boats tied to the northern pier | count |
| pq_count_people_see | כמה אנשים אתה רואה | how many people do you see | count |
| pq_count_cars_see | כמה מכוניות אתה רואה בזירה | how many cars do you see in the scene | count |
| pq_count_vehicles_road | כמה רכבים אתה רואה על הכביש | how many vehicles do you see on the road | count |
| pq_count_windows_see | כמה חלונות אתה רואה בבניין | how many windows do you see on the building | count |
| pq_count_buildings | ספור את הבניינים בזירה | count the buildings in the scene | count |
| p75_count_entrance | כמה אנשים עומדים ליד הכניסה | How many people are standing near the entrance | count |
| p75_count_cars_behind_white | כמה מכוניות חונות מאחורי הבניין הלבן | How many cars are parked behind the white building | count |
| lp_look_down | תסתכל למטה בבקשה | Look down please | describe |
| pq_see_now | מה אתה רואה עכשיו | what do you see now | describe |
| pq_see_frame | מה אתה רואה בפריים | what do you see in the frame | describe |
| pq_see_suspicious | מה אתה רואה חשוד בזירה | what suspicious thing do you see in the scene | describe |
| pq_see_ahead | מה אתה רואה לפניך | what do you see ahead of you | describe |
| pq_any_person | האם יש אדם בתמונה | is there a person in the picture | describe |
| pq_any_vehicle | האם יש רכב בזירה | is there a vehicle in the scene | describe |
| pq_any_red_car | האם יש מכונית אדומה בפריים | is there a red car in the frame | describe |
| pq_any_roof_person | האם יש מישהו על הגג | is there anyone on the roof | describe |
| pq_any_weapon | האם יש מישהו חמוש בזירה | is there anyone armed in the scene | describe |
| pq_any_backpack_left | האם יש תיק גב בצד שמאל | is there a backpack on the left side | describe |
| pq_any_movement | האם יש תנועה בזירה | is there movement in the scene | describe |
| pq_whats_in_frame | מה נמצא בפריים | what is in the frame | describe |
| pq_whats_ahead | מה נמצא לפניך | what is ahead of you | describe |
| pq_describe_scene | תאר את מה שאתה רואה בזירה | describe what you see in the scene | describe |
| pq_identify_threats | זהה איומים אפשריים בזירה | identify possible threats in the scene | describe |
| pq_look_ground | הסתכל על הקרקע ותאר מה יש | look at the ground and describe what is there | describe |
| pq_identify_color | זהה את הצבע של הרכב הקרוב ביותר | identify the color of the nearest vehicle | describe |
| p75_describe_right | תאר לי מה יש מימין | Describe what is on the right | describe |
| p75_anyone_armed | יש כאן מישהו עם נשק? | Is there anyone here with a weapon? | describe |
| p75_look_right | תסתכל ימינה | Look to the right | describe |
| s_gentle_scan | תעשה לי סריקה עדינה על הגזרה | Do a gentle scan over the sector | describe |

Highlight (110):

| case | Hebrew | English gloss | proposed kind |
|---|---|---|---|
| i_mid_windows | הדגש את החלונות האמצעיים של הבניין הימני ביותר | Highlight the middle windows of the rightmost building | highlight |
| i_third_door | סמן את הדלת הקדמית של הבית השלישי משמאל | Mark the front door of the third house from the left | highlight |
| i_rear_wheel | התמקד בגלגל האחורי של האופנוע החונה | Focus on the rear wheel of the parked motorcycle | highlight |
| i_roof_corner | סמן את הפינה השמאלית העליונה של הגג האדום | Mark the top left corner of the red roof | highlight |
| i_chimney | הדגש את הארובה של הבית הנמוך ביותר ברחוב | Highlight the chimney of the lowest house on the street | highlight |
| i_back_entrance | מצא את הכניסה האחורית של המחסן הגדול | Find the back entrance of the big warehouse | highlight |
| i_ladder_pickup | סמן את הסולם שעל הגג של הטנדר הלבן | Mark the ladder on the roof of the white pickup | highlight |
| i_car_by_red | הדגש את המכונית שצמודה לאדם עם הלבוש האדום | Highlight the car adjacent to the person with the red attire | highlight |
| i_orange_cap | עקוב אחרי האדם עם הכובע הכתום | Track the person with the orange cap | highlight |
| i_door_by_coat | סמן את הדלת שליד האיש עם המעיל השחור | Mark the door next to the man with the black coat | highlight |
| i_bike_fence | התמקד באופניים שנשענים על הגדר של הבית הצהוב | Focus on the bicycle leaning on the fence of the yellow house | highlight |
| i_dog_by_dress | עקוב אחרי הכלב שהולך ליד האישה עם השמלה הלבנה | Track the dog walking beside the woman in the white dress | highlight |
| i_kid_bag | הדגש את התיק שמחזיק הילד עם החולצה הירוקה | Highlight the bag that the child with the green shirt is holding | highlight |
| i_tree_truck | סמן את העץ שמאחורי המשאית הצהובה | Mark the tree behind the yellow truck | highlight |
| i_win_over_door | מצא את החלון שמעל הדלת הכחולה | Find the window above the blue door | highlight |
| i_bench_trees | הדגש את הספסל שבין שני העצים הגבוהים | Highlight the bench between the two tall trees | highlight |
| i_behind_moto | עקוב אחרי הרכב שנוסע מאחורי האופנוע האדום | Track the vehicle driving behind the red motorcycle | highlight |
| i_man_on_roof | סמן את האיש שעומד על הגג של הבניין הלבן | Mark the man standing on the roof of the white building | highlight |
| i_box_by_man | הדגש את התיבה שליד האיש שעומד על הגג של הבניין הלבן | Highlight the box next to the man standing on the roof of the white building | highlight |
| i_girl_balloon | עקוב אחרי הילדה עם הבלון שהולכת ליד האישה עם העגלה | Track the girl with the balloon walking near the woman with the stroller | highlight |
| i_car_between | סמן את המכונית החונה בין הטנדר הלבן למשאית האדומה | Mark the car parked between the white pickup and the red truck | highlight |
| i_door_by_tree | מצא את הדלת של הבית שמול העץ הגבוה ביותר | Find the door of the house facing the tallest tree | highlight |
| i_sign_awning | התמקד בשלט שמעל הכניסה של החנות עם הסוכך הירוק | Focus on the sign above the entrance of the store with the green awning | highlight |
| i_front_tire | הדגש את הצמיג הקדמי של המכונית שחונה הכי קרוב לשער | Highlight the front tire of the car parked closest to the gate | highlight |
| i_exit_gray | עקוב אחרי האדם שיצא מהדלת של הבניין האפור | Track the person who came out of the door of the gray building | highlight |
| i_second_car | סמן את הרכב השני משמאל בשורה הקדמית של החניון | Mark the second vehicle from the left in the front row of the parking lot | highlight |
| i_dark_stain | מצא את הכתם הכהה על הקיר שמימין לחלון הגדול | Find the dark stain on the wall to the right of the big window | highlight |
| i_glasses_talk | הדגש את האיש עם המשקפיים שמדבר עם האישה בחולצה הצהובה | Highlight the man with the glasses talking to the woman in the yellow shirt | highlight |
| i_truck_boat | עקוב אחרי המשאית שגוררת את הסירה הלבנה | Track the truck towing the white boat | highlight |
| i_empty_chair | סמן את הכיסא הריק ליד השולחן העגול | Mark the empty chair next to the round table | highlight |
| i_bird_cable | התמקד בציפור שיושבת על הכבל בין שני העמודים | Focus on the bird sitting on the cable between the two poles | highlight |
| i_fence_gap | מצא את הפתח בגדר שמאחורי המכולה הכחולה | Find the opening in the fence behind the blue container | highlight |
| i_helmet_mid | הדגש את הרוכב עם הקסדה הצהובה שנמצא במרכז הקבוצה | Highlight the rider with the yellow helmet in the middle of the group | highlight |
| i_cat_climb | עקוב אחרי החתול שמטפס על העץ שליד החומה | Track the cat climbing the tree next to the wall | highlight |
| i_lean_silver | סמן את הבחור שנשען על המכונית הכסופה | Mark the guy leaning on the silver car | highlight |
| i_flag_low | מצא את הדגל שמתנוסס מעל הגג של המבנה הנמוך | Find the flag flying above the roof of the low structure | highlight |
| i_broken_window | הדגש את החלון השבור בקומה התחתונה של הבניין הנטוש | Highlight the broken window on the bottom floor of the abandoned building | highlight |
| i_last_convoy | עקוב אחרי המכונית האחרונה בשיירה | Track the last car in the convoy | highlight |
| i_big_tent | סמן את האוהל הגדול ביותר בקצה השדה | Mark the biggest tent at the edge of the field | highlight |
| i_crane_arm | התמקד בזרוע של המנוף שמעל אתר הבנייה | Focus on the arm of the crane above the construction site | highlight |
| j_bag_chain | הדגש את התיק שמונח ליד הכיסא שמאחורי הדלפק של החנות עם הסוכך הכחול | Highlight the bag lying next to the chair behind the counter of the store with the blue awning | highlight |
| j_bird_branch | סמן את הציפור שעל הענף של העץ שליד הכניסה לבניין האפור | Mark the bird on the branch of the tree next to the entrance of the gray building | highlight |
| j_kid_ball | עקוב אחרי הילד עם הכדור שרץ ליד הגדר של המגרש שמאחורי בית הספר | Track the kid with the ball running along the fence of the field behind the school | highlight |
| j_win_gas | התמקד בחלון השבור בקומה השנייה של הבית שמול תחנת הדלק | Focus on the broken window on the second floor of the house opposite the gas station | highlight |
| j_hat_bench | מצא את הכובע שנפל ליד הספסל שמתחת לעץ הגדול בפינת הפארק | Find the hat that fell next to the bench under the big tree at the corner of the park | highlight |
| j_flag_mast | סמן את הדגל הקטן שעל התורן של הסירה שקשורה למזח הדרומי | Mark the small flag on the mast of the boat tied to the southern pier | highlight |
| j_sticker | הדגש את המדבקה שעל הפגוש של המכונית שחונה מאחורי המשאית הירוקה | Highlight the sticker on the bumper of the car parked behind the green truck | highlight |
| j_dog_steps | עקוב אחרי הכלב הקטן שמשחק ליד הילדה שיושבת על המדרגות של הבית הלבן | Track the small dog playing near the girl sitting on the steps of the white house | highlight |
| j_lock_gate | התמקד במנעול שעל השער של הגדר שמקיפה את המגרש הריק | Focus on the lock on the gate of the fence surrounding the empty lot | highlight |
| j_helmet_seat | מצא את הקסדה שמונחת על המושב של האופנוע שחונה ליד הכניסה לחניון | Find the helmet on the seat of the motorcycle parked near the entrance of the parking garage | highlight |
| j_sign_between | סמן את השלט הקטן שמעל הדלת של החנות שבין המסעדה לבנק | Mark the small sign above the door of the store between the restaurant and the bank | highlight |
| j_drainpipe | הדגש את הצינור שיורד מהגג של הבית שליד עמוד החשמל הגבוה | Highlight the drainpipe coming down from the roof of the house next to the tall pole | highlight |
| j_umbrella_x | עקוב אחרי האישה עם המטרייה האדומה שחוצה את הכביש ליד הרמזור | Track the woman with the red umbrella crossing the road near the traffic light | highlight |
| j_hole_wall | התמקד בחור שבקיר של המבנה הישן שמאחורי מגרש החניה | Focus on the hole in the wall of the old structure behind the parking lot | highlight |
| j_tilt_sign | מצא את התמרור שנוטה הצידה ליד הפנייה לרחוב עם העצים | Find the road sign leaning sideways near the turn to the street with the trees | highlight |
| j_crate_trunk | סמן את הארגז שמציץ מתא המטען של הרכב שחונה מול השער הצהוב | Mark the crate sticking out of the trunk of the vehicle parked opposite the yellow gate | highlight |
| j_mural | הדגש את הציור שעל הקיר של הבניין שמימין לגשר להולכי הרגל | Highlight the painting on the wall of the building to the right of the pedestrian bridge | highlight |
| j_cat_jump | עקוב אחרי החתול שקופץ מהגדר אל הגג של המחסן שבחצר האחורית | Track the cat jumping from the fence onto the roof of the shed in the backyard | highlight |
| j_faucet | התמקד בברז שבצד של הבית שליד הערוגה עם הפרחים האדומים | Focus on the faucet on the side of the house next to the flowerbed with the red flowers | highlight |
| j_truck_text | מצא את הכיתוב שעל הדופן של המשאית שעוצרת ליד תחנת האוטובוס המקורה | Find the lettering on the side of the truck stopping near the covered bus stop | highlight |
| j_pin_busstop | עקוב אחרי האיש עם החולצה הכחולה, זה שעומד ליד תחנת האוטובוס, בצד השמאלי של המסך, קרוב לספסל | Track the man with the blue shirt, the one standing next to the bus station, on the left side of the frame, close to the bench | highlight |
| j_pin_notmoving | סמן את המכונית הלבנה, לא זו שנוסעת, זו שחונה ליד המדרכה, עם הדלת הפתוחה | Mark the white car, not the one driving, the one parked next to the sidewalk, with the open door | highlight |
| j_pin_antennas | הדגש את הבניין הגבוה, זה עם האנטנות על הגג, שנמצא מאחורי מגרש המשחקים, קצת ימינה מהמרכז | Highlight the tall building, the one with the antennas on the roof, behind the playground, slightly to the right of the center | highlight |
| j_pin_drone2 | עקוב אחרי הרחפן השני, הקטן יותר, שטס נמוך מעל השדה, ליד קו העצים | Track the second drone, the smaller one, flying low over the field, near the tree line | highlight |
| j_pin_leash | מצא את הכלב החום, עם הרצועה האדומה, שמשחק על הדשא, בין שני הספסלים, ליד השביל | Find the brown dog, with the red leash, playing on the grass, between the two benches, near the path | highlight |
| j_pin_window3 | התמקד בחלון השלישי מימין, בקומה השנייה, של הבניין עם הקירות הצהובים, זה שליד בית הקפה | Focus on the third window from the right, on the second floor, of the building with the yellow walls, the one next to the coffee shop | highlight |
| j_pin_notphone | סמן את האדם שעומד הכי קרוב לכניסה, עם התיק הגדול, לא זה עם הטלפון | Mark the person standing closest to the entrance, with the big bag, not the one with the phone | highlight |
| j_pin_2riders | עקוב אחרי האופנוע השחור, זה עם שני הרוכבים, שנוסע בנתיב הימני, לכיוון הצומת | Track the black motorcycle, the one with the two riders, driving in the right lane, toward the intersection | highlight |
| j_pin_bluedoor | הדגש את הדלת הכחולה, השלישית משמאל, בשורת החנויות, ליד הדוכן של הפירות | Highlight the blue door, the third from the left, in the row of shops, next to the fruit stand | highlight |
| j_pin_smallbike | מצא את הילד עם הכובע האדום, זה שרוכב על אופניים קטנים, על השביל, ליד הברזייה | Find the kid with the red cap, the one riding the small bicycle, on the path, near the drinking fountain | highlight |
| j_pin_roofnear | סמן את הגג של הבית הכי קרוב אליך, זה עם הסולם שנשען עליו | Mark the roof of the house closest to you, the one with the ladder leaning on it | highlight |
| j_pin_leaving | עקוב אחרי המשאית הכתומה שיוצאת עכשיו מהאתר, זו עם הארגז הפתוח | Track the orange truck leaving the site now, the one with the open box | highlight |
| j_pin_flagman | הדגש את האיש בקצה הימני של הקבוצה, זה עם הכובע, שמחזיק את הדגל | Highlight the man at the right edge of the group, the one with the hat, holding the flag | highlight |
| j_pin_notsail | התמקד בסירה הקטנה עם המנוע, לא במפרשית, זו שקרובה יותר לחוף | Focus on the small boat with the motor, not the sailboat, the one closer to the shore | highlight |
| j_pin_bushes | מצא את הפתח בגדר, בערך באמצע שלה, איפה שהשיחים נמוכים | Find the gap in the fence, around the middle of it, where the bushes are low | highlight |
| j_pin_campole | סמן את העמוד עם המצלמה, זה שנמצא בפינה של החניון, ליד היציאה | Mark the pole with the camera, the one at the corner of the parking lot, near the exit | highlight |
| j_pin_fastwalk | עקוב אחרי האישה עם המעיל הארוך, זו שהולכת מהר, בצד הרחוק של הכיכר | Track the woman with the long coat, the one walking fast, on the far side of the square | highlight |
| j_pin_planks | הדגש את הערימה של הקרשים, ליד הקיר האחורי, מתחת לחלון | Highlight the pile of wooden planks, near the back wall, under the window | highlight |
| j_pin_halfgate | התמקד בשער הכחול בקצה השביל, זה שחצי פתוח | Focus on the blue gate at the end of the path, the one that is half open | highlight |
| j_pin_spare | מצא את הצמיג הרזרבי שמחובר לחלק האחורי של הגיפ האפור | Find the spare tire attached to the back of the gray jeep | highlight |
| j_pin_stage3 | סמן את הקבוצה של שלושת האנשים שעומדים הכי קרוב לבמה, משמאל לרמקול הגדול | Mark the group of three people standing closest to the stage, to the left of the big speaker | highlight |
| j_pin_hay | עקוב אחרי הטרקטור הירוק שעובד בשדה, זה שגורר את העגלה עם החציר | Track the green tractor working in the field, the one towing the cart with the hay | highlight |
| j_pin_fullbin | הדגש את הפח הכתום ליד הכניסה האחורית, זה שמלא עד למעלה | Highlight the orange bin next to the back entrance, the one that is full to the top | highlight |
| j_pin_wirebirds | התמקד בציפורים שיושבות על החוטים, רק אלה שמעל הכביש, לא אלה שמעל המדרכה | Focus on the birds sitting on the wires, only the ones above the road, not the ones above the sidewalk | highlight |
| j_pin_extstairs | מצא את המדרגות החיצוניות בצד של הבניין, אלה שמובילות לגג | Find the outdoor stairs on the side of the building, the ones leading to the roof | highlight |
| j_pin_wrongway | סמן את הרכב היחיד בחניון שחונה הפוך, עם הפנים ליציאה | Mark the only car in the parking lot parked the wrong way, facing the exit | highlight |
| j_pin_firstrun | עקוב אחרי הקבוצה של הרצים, ספציפית אחרי זה עם האפוד הצהוב שרץ ראשון | Track the group of runners, specifically the one with the yellow vest running first | highlight |
| j_pin_barrel | הדגש את החבית שמונחת על הצד, ליד ערימת החול, מאחורי הבטונדות | Highlight the barrel lying on its side, next to the pile of sand, behind the concrete barriers | highlight |
| j_pin_puddle | התמקד בשלולית הגדולה באמצע הדרך, זו שמשקפת את הבניין | Focus on the big puddle in the middle of the road, the one reflecting the building | highlight |
| j_pin_scaffold | מצא את הסולם הכי גבוה בין אלה שנשענים על הפיגום, בצד המערבי | Find the tallest ladder among the ones leaning on the scaffolding, on the west side | highlight |
| j_pin_idledozer | סמן את הדחפור הצהוב שעומד בלי לזוז ליד הבור הגדול, לא את זה שעובד | Mark the yellow bulldozer standing still next to the big pit, not the one that is working | highlight |
| j_pin_cart | עקוב אחרי העגלה של הקניות שמישהו דוחף במעלה הרחוב, ליד המכוניות החונות | Track the shopping cart someone is pushing up the street, near the parked cars | highlight |
| j_pin_graffiti | הדגש את הכתובת שרשומה על הקיר, מתחת לחלון השני משמאל | Highlight the writing on the wall, under the second window from the left | highlight |
| j_pin_ferris | התמקד בגלגל הענק בקצה הפארק, ספציפית בתא התחתון שלו | Focus on the ferris wheel at the edge of the park, specifically its bottom cabin | highlight |
| j_pin_planters | מצא את שני העציצים הגדולים משני צידי הדלת הראשית של המלון | Find the two large planters on both sides of the main door of the hotel | highlight |
| lp_white_car | תעקוב אחרי המכונית הלבנה | Follow the white car | highlight |
| lp_nearest_person | תדגיש את האדם שהכי קרוב אליך | Highlight the person closest to you | highlight |
| pq_find_people | מצא את כל האנשים בפריים | find all the people in the frame | highlight |
| pq_search_vehicle | חפש רכב חשוד באזור | search for a suspicious vehicle in the area | highlight |
| pq_focus_describe | התמקד באדם הקרוב ותאר אותו | focus on the nearest person and describe them | highlight |
| p75_open_window_2nd | סמן את החלון הפתוח בקומה השנייה | Mark the open window on the second floor | highlight |
| p75_follow_blue_bike | עקוב אחרי האופניים הכחולים | Follow the blue bicycle | highlight |
| p75_all_vehicles | הדגש את כל הרכבים | Highlight all the vehicles | highlight |
| p75_purple_bag | סמן את האדם עם התיק הסגול | Mark the person with the purple bag | highlight |
| p75_approach_blue_car | התקרב לרכב הכחול | Get closer to the blue car | highlight |
| s_eye_junction | שים עין על הצומת ואל תרד ממנו | Keep an eye on the junction and do not come off it | highlight |
| s_zoom_suspect | תן זום על הרכב החשוד ותחזיק אותו במרכז | Zoom in on the suspicious vehicle and hold it in the center | highlight |
| s_eyes_on | תדווח כשיש לך עיניים על המטרה | Report when you have eyes on the target | highlight |
| s_obs_report | החזק תצפית על הבית הלבן, דווח כל תזוזה, עבור | Maintain observation on the white house, report any movement, over | highlight |
| s75_observe_junction | תן לי תצפית על הצומת ודווח | Give me an observation of the junction and report | highlight |

Recordings (datasets/asr/recordings.json): 14 perception clips carried the kind the owner chose
on the page as their first keyword group; that group moved into `vision` (the owner's own
choice, not a draft). 14 others were saved with no kind; their drafts follow the nearest case:

| clip | Hebrew | nearest case | proposed kind |
|---|---|---|---|
| session-20260908-170015-rog__audio_00000 | הדגש את התיבה שליד האיש שעומד על הגג של הבניין הלבן | i_box_by_man | highlight |
| session-20260908-170015-rog__audio_00000 | התמקד בשלולית הגדולה באמצע הדרך, זו שמשקפת את הבניין | j_pin_puddle | highlight |
| session-20260908-170015-rog__audio_00000 | סמן את החלון הפתוח בקומה השנייה | p75_open_window_2nd | highlight |
| session-20260908-170015-rog__audio_00000 | התמקד בחלון השבור בקומה השנייה של הבית שמול תחנת הדלק | j_win_gas | highlight |
| session-20260908-170015-rog__audio_00001 | סמן את המכונית החונה בין הטנדר הלבן למשאית האדומה | i_car_between | highlight |
| session-20260908-170015-rog__audio_00001 | הדגש את הציור שעל הקיר של הבניין שמימין לגשר להולכי הרגל | j_mural | highlight |
| session-20260908-170015-rog__audio_00001 | זהה את הצבע של הרכב הקרוב ביותר | pq_identify_color | describe |
| session-20260908-170015-rog__audio_00002 | עקוב אחרי האופנוע השחור, זה עם שני הרוכבים, שנוסע בנתיב הימני, לכיוון הצומת | j_pin_2riders | highlight |
| session-20260908-170015-rog__audio_00002 | הדגש את האיש עם המשקפיים שמדבר עם האישה בחולצה הצהובה | i_glasses_talk | highlight |
| session-20260908-170015-rog__audio_00002 | סמן את האיש שעומד על הגג של הבניין הלבן. | i_man_on_roof | highlight |
| session-20260908-170015-rog__audio_00003 | הדגש את התיק שמחזיק הילד עם החולצה הירוקה | i_kid_bag | highlight |
| session-20260908-170015-rog__audio_00003 | התמקד בחלון השלישי מימין, בקומה השנייה, של הבניין עם הקירות הצהובים, זה שליד בית הקפה | j_pin_window3 | highlight |
| session-20260908-170015-rog__audio_00003 | הדגש את הבניין הגבוה, זה עם האנטנות על הגג, שנמצא מאחורי מגרש המשחקים, קצת ימינה מהמרכז | j_pin_antennas | highlight |
| session-20260908-170015-rog__audio_00003 | ספור את הסירות הקשורות למזח הצפוני | i_boats_pier | count |

## OPEN
- R1 (the military set, 0/21): its keyword groups grade a translation; the recognizer routes these
  sentences, so the set measures nothing about it. Options: (a) keep it as converted, as V3 said
  (recommended until the owner rules); (b) give each sentence an expected kind (mission, vision
  request or reject) and grade that; (c) leave it out of the default run.
- R2 (two homes of the live lists): datasets/e2e/*.md are the lists a person speaks;
  datasets/recognizer/live-test-*.json hold the same sentences, graded. Options: (a) keep both:
  the .md is for speaking, the JSON for grading (recommended); (b) delete the .md files and speak
  from the JSON.
- R3 (util/mission.py): only app/turns.py uses it now. Options: (a) move step_text into app/ in
  the layout task D (recommended); (b) leave it in util/.
- R4 (scoring choices of the new scorer, mine, not ruled): a Gemma failure is always a FAIL; a
  halt passes a "none" case; an "open" case passes only when a mission flies (as unified_bench
  did). Options: (a) keep (recommended); (b) name what to change.

## For the owner
- J5 (2026-09-29): the tool refused `rm` of the old spoken lists (their content is in
  datasets/recognizer/: the sentences in the topical files, the order in the live lists). Please run:
  ```
  rm -r /root/groundstation/datasets/e2e
  ```
  bench/whole-system/run_all.sh still names datasets/e2e; it is retired (B6) and perf holds it.
- The tool refused `rm` (B1 deletions). Please run:
  ```
  rm /root/groundstation/bench/hebrew-command-bench/unified_bench.py /root/groundstation/bench/whole-system/run_list.py /root/groundstation/projects/integration_harden2/log/score.py
  ```
  Every reference to them in code and docs is already removed or updated (run.sh and the docs
  held by perf follow when perf releases them).

## Progress
- Model: claude-opus-5-5[1m] (Opus 5.5); CLAUDE_EFFORT=medium.

### A1 checkpoint (2026-09-28): route() decides, act() acts
- Files: recognizer/recognizer.py (Decision; route(); act(); handle() = act(route());
  _decide_without_model / _decide_plan / _decide_mission replace the _route_* methods),
  recognizer/__init__.py (exports Decision), recognizer/README.md,
  docs/api-harden2/recognizer.h (v2.4: Decision, RecognizerRoute, RecognizerAct),
  test/test_recognizer.py (one NEW test at the end; no existing test changed).
- Checks:
  - flake8: my files clean. The whole tree prints 6 E501 lines, all in perf's files in progress
    (app/main.py:20, config/constants.py:140-143, log/perf.py:83, test/test_app.py:316).
  - pyflakes: clean. Audit: "except handlers: 5".
  - Suite run 1: "3 failed, 213 passed, 2 skipped" (test_log.py perf-report tests: perf's C1 in
    progress). Suite run 2: "220 passed, 2 skipped".
  - test_recognizer.py alone: "41 passed".
- Mutation check: route() made to call act() -> "5 failed, 36 passed" (the new test among them);
  restored.
- Change impact:

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| handle() split into route() + act() | none: the app calls handle() as before | no | the 40 old tests pass unchanged |
| route() returns a Decision, sends nothing | new API for the benchmark | additive | new: test_route_decides_and_sends_nothing |
| the log's `kind` field for critical words is set in route() instead of _critical() | same field, same value | no | none |

- Y2: benchmarks importing recognizer: bench/hebrew-command-bench/{unified_bench, real_cadence,
  type_english, contention, perf, type_compare, type_fresh}.py and bench/whole-system/run_list.py.
  They call plan(), recognize_direct(), numbers_vs_mission(), is_shot_echo(): all unchanged.
- Self-check vs 9d A1: route() decides and sends nothing (test + mutation); handle() = route +
  act; tests in test_recognizer.py pass unchanged; recognizer.h synced. Done.
- Proposed HISTORY entry: "2026-09-28 -- the recognizer decides, then acts. Why: owner 1.8, D3.
  Result: route() -> Decision sends nothing; act() carries it out; handle() = both. 40 old tests
  unchanged; one new test, mutation-checked. Where: recognizer/recognizer.py."

### B1 checkpoint (2026-09-28): the recognizer benchmark
- Files (new): bench/recognizer/accuracy.py (197 lines), bench/recognizer/scorer.py (157 lines),
  bench/recognizer/README.md, bench/recognizer/results/2026-09-28-{baseline,a2,a2b}-*.{json,md},
  datasets/recognizer/{commands,verbose,emergency,perception,military,live-test-50,
  live-test-75,live-test-e2e-50,live-test-subset,numbers}.json.
- Files (changed): run.sh (the score command and its lines gone), docs/spec-harden2-run-arguments.md
  (the score row and line gone; a pointer to the benchmark), projects/integration_harden2/README.md
  (log/ row), log/__init__.py, log/session_files.py, util/mission.py (docstrings),
  docs/api-harden2/log.h (the score.py line), bench/README.md (the list),
  recognizer/README.md (the sync rule points at accuracy.py).
- NOT deleted (the tool refused rm; the command is under "For the owner"):
  bench/hebrew-command-bench/unified_bench.py, bench/whole-system/run_list.py, log/score.py.
  Nothing imports them any more.
- Verification on real Gemma (gpu locked, 03:47-03:53): ALL 592 PASS / 94 FAIL / 43 REVIEW;
  live-test-50 32 / 0 / 18 against 30 / 2 / 18 on 2026-09-26 (lines 21 and 26 now PASS: "+90"
  read). commands 240/254, verbose 59/63, perception 102/138, emergency 12/12 match the
  2026-09-19 scorecard (240/253, 59/63, 101/138, 12/12).
- Checks: see the A2 checkpoint (run after both).
- Change impact:

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| bench/recognizer/ (new) | none in the app | additive | no benchmark tests (Y2 b) |
| `run.sh score` removed | the score command | yes, by ruling U2.3 | none (no test used it) |
| log/score.py to delete | a read-only tool | yes, by ruling U2.3 | none |

- Y2: benchmarks importing a changed module: none import scorer/accuracy; bench.py (B7) no
  longer needed by B1.
- Self-check vs 9d B1: JSON files as they are (V3) yes; the verbose set generated once yes;
  path A yes; one scorer in bench/recognizer, reads "+90" yes; kind + target words for
  perception yes; a file argument yes; calls route() yes; README (why, run, results) yes;
  verified on Gemma and compared yes; deletions: run.sh score done, the three files wait on
  the owner's rm.
- Proposed HISTORY entry: "2026-09-28 -- one recognizer benchmark, through route(). Why: U2,
  U2.3, D3. Setup: bench/recognizer/accuracy.py; 729 sentences in datasets/recognizer/; Gemma 4
  E4B, thinking off. Result: 592 PASS / 94 FAIL / 43 REVIEW; live-test-50 32/0/18 (was 30/2/18:
  the "+90" notation is read). Verdict: the benchmark replaces unified_bench.py, run_list.py and
  log/score.py. Where: bench/recognizer/."

### A2 checkpoint (2026-09-28): the numbers
- Files: util/hebrew.py (FRONT_LETTERS, UNIT_WORDS, FRACTIONS, FRACTION_PLURALS, split_front;
  hebnum_to_digits(s, front_letters=False); two units in a row are two numbers),
  recognizer/numbers.py (is_number_word, is_number_token, read_fractions, nums_he),
  recognizer/guards.py (numbers_vs_mission within 0.01), recognizer/README.md,
  datasets/recognizer/numbers.json (40 sentences), test/test_recognizer.py (5 new tests),
  test/README.md.
- Measured first (T5), the guard offline, Gemma on the gpu: the guard read 7 of 40 right; Gemma
  planned 29 of 40 through route(). Gemma planned all 23 front-letter sentences right; the guard
  read none of them (so any number would have passed). On the fractions the guard rejected 9
  right plans.
- After: the guard reads 40 of 40. Gemma through route(): numbers 38/40; ALL 602 / 84 / 43.
  The 2 FAILs are Gemma's (an eighth); one is now rejected by the guard. Outside numbers.json
  only l75_turn270 changed (FAIL -> PASS). Over the 398 exact-mission cases, the guard rejects
  2 right plans (was 12): r_z_03 (centimetres) and l75_v_self_correct (a self-correction), both
  by design.
- A first variant also wrote a prefixed number as digits for Gemma ("ב-5"): 601 / 85 / 43, one
  loss (two steps fused into a diagonal). Stage 2 now leaves those words to Gemma.
- Checks: flake8 clean (rc 0, the whole tree); pyflakes clean; audit "except handlers: 5";
  suite run 1 "229 passed, 2 skipped"; run 2 "229 passed, 2 skipped"; bench/recognizer lint clean.
- Mutation checks (each broke one test or more, then restored): drop כ from FRONT_LETTERS;
  drop רבע; drop שמינית; tolerance 0; let two units compose; convert an ordinal with ה; stage 2
  converts prefixes by default; the guard ignores prefixes.
- Change impact:

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| guard reads the seven front letters | a plan with a prefixed number | stricter: a wrong number is now rejected | new tests |
| guard reads fractions | a plan with a fraction | fewer false rejects (9 of 11) | new tests |
| guard compares within 0.01 | a third | fewer false rejects | new test |
| a fraction of a metre is not a bare metre | the text Gemma reads ("רבע מטר" no longer gets "אחד") | fixes a wrong text | new test |
| two units in a row are two numbers | "אחד וחמישה" | fixes 5 -> 1, 5 | new test |
| stage 2 text for prefixed words | none (unchanged) | no | old tests unchanged |

- Y2: benchmarks importing recognizer/util.hebrew: bench/recognizer (re-measured above);
  bench/hebrew-command-bench/{bench, perf, type_*, real_cadence, contention}.py call
  recognize_direct / plan (signatures unchanged).
- Self-check vs 9d A2: a sentence set with fractions (quarter, third, eighth, half) and all
  seven front letters: yes (numbers.json); Gemma and the guard measured first: yes; the tables
  completed in numbers.py and util/hebrew.py: yes; re-measured: yes.
- Proposed HISTORY entry: "2026-09-28 -- the number guard reads all seven front letters and the
  fractions. Why: C.3, Q8, R8, T5. Setup: 40 sentences (datasets/recognizer/numbers.json), the
  guard offline, Gemma 4 E4B through route(). Result: before, the guard read 7/40 and Gemma
  passed 29/40 (Gemma right on 23/23 front-letter sentences; the guard rejected 9 right fraction
  plans); after, the guard reads 40/40 and 38/40 pass; the whole benchmark 592 -> 602 PASS, no
  case lost. Verdict: the guard reads numbers, Gemma keeps the words. Where: util/hebrew.py,
  recognizer/numbers.py, recognizer/guards.py."
- All three tasks done. Waiting only on the owner's rm (For the owner).

### Brief 2 checkpoint (2026-09-29): J5, the J1 + J4 drafts, TR1, TR3, TR5
- J5 files: datasets/recognizer/{commands,emergency,perception}.json (+19 sentences; commands
  lost its copies question and question2, whose home is perception.json: pq_see_now,
  pq_count_people_see); datasets/recognizer/live-test-{50,75,e2e-50,subset}.json rewritten in
  place as ordered name lists ({"list", "source", "cases": [names]}; in place because rm is
  refused); datasets/asr/recordings.json (its one case re-pointed at perception.json /
  i_box_by_man with its keyword groups); bench/recognizer/accuracy.py (topical files by default,
  each sentence once; --list NAME; --print NAME with python-bidi; a live list resolves through
  the case names, a name used twice dies); scorer.py ("either way" -> ["abs", n]; `alternatives`;
  "halt" as an alternative, owner J4 rule 2); confirm.py (skips live lists: its pool is now 545
  distinct sentences, was 729 with copies); bench/recognizer/README.md; bench/README.md.
- J5 counts: 545 sentences, each once (commands 267, verbose 63, emergency 13, perception 141,
  military 21, numbers 40). The 19 new ones: the 15 only live-test-50 held + its 4 unnumbered
  bonus lines. live-test-50 has 54 names (the bonus lines at its end), 75, 50, 26.
- J5 merge: 64 copies disagreed. An exact result beat "review"/"open" in 2 (square, r_dis4:
  "open" -> "none" from the subset's "must NOT fly"); the topical result was kept in 37
  (the live copy said "review", or l75_v_climb_then_count: topical dz+3 vs the list's note of
  what happened); r_mis5 now agrees ("either way" read as ["abs", 180]). The topical keyword
  groups won in 23 (the live copy had none):

| case | Hebrew | keyword groups kept |
|---|---|---|
| pq_see_now | מה אתה רואה עכשיו | see/look + now |
| p75_follow_blue_bike | עקוב אחרי האופניים הכחולים | bicycle/bike + blue + follow/track |
| p75_count_entrance | כמה אנשים עומדים ליד הכניסה | how many/count + people/person/men + entrance/door/entry |
| p75_describe_right | תאר לי מה יש מימין | describe/tell + right |
| s75_observe_junction | תן לי תצפית על הצומת ודווח | observ/watch/view + junction/intersection + report |
| p75_all_vehicles | הדגש את כל הרכבים | vehicle/car + all/every |
| p75_purple_bag | סמן את האדם עם התיק הסגול | person/man/people + bag/backpack + purple/violet |
| i_box_by_man | הדגש את התיבה שליד האיש שעומד על הגג של הבניין הלבן | box/crate/chest + next/beside/near + man/person + stand + roof + building + white |
| j_pin_puddle | התמקד בשלולית הגדולה באמצע הדרך, זו שמשקפת את הבניין | puddle/pool/water + big/large + middle/center + road/street/path + reflect + building |
| j_win_gas | התמקד בחלון השבור בקומה השנייה של הבית שמול תחנת הדלק | window + broken + second + floor/story/storey + house/home/building + opposite/facing/across/front + gas/fuel/petrol + station |
| i_car_between | סמן את המכונית החונה בין הטנדר הלבן למשאית האדומה | car/vehicle + park + between + white + pickup/van + red + truck/lorry |
| j_mural | הדגש את הציור שעל הקיר של הבניין שמימין לגשר להולכי הרגל | paint/mural/graffiti/drawing + wall + building + right + pedestrian/foot + bridge |
| pq_identify_color | זהה את הצבע של הרכב הקרוב ביותר | identif/spot + color/colour + vehicle/car + near/nearest/close |
| j_pin_2riders | עקוב אחרי האופנוע השחור, זה עם שני הרוכבים, שנוסע בנתיב הימני, לכיוון הצומת | motorcycle/motorbike + black + two + rider/passenger + right + lane + intersection/junction/crossroad |
| i_glasses_talk | הדגש את האיש עם המשקפיים שמדבר עם האישה בחולצה הצהובה | man/person + glasses + talk/speak/convers + woman/lady + yellow + shirt |
| i_man_on_roof | סמן את האיש שעומד על הגג של הבניין הלבן | man/person + stand + roof + building + white |
| i_kid_bag | הדגש את התיק שמחזיק הילד עם החולצה הירוקה | bag/backpack + hold/carry + child/kid/boy + green + shirt |
| j_pin_window3 | התמקד בחלון השלישי מימין, בקומה השנייה, של הבניין עם הקירות הצהובים, זה שליד בית הקפה | window + third + right + second + floor/story/storey + yellow + wall + coffee/cafe |
| j_pin_antennas | הדגש את הבניין הגבוה, זה עם האנטנות על הגג, שנמצא מאחורי מגרש המשחקים, קצת ימינה מהמרכז | building + tall/high + antenna + roof + behind + playground + right + center/middle |
| i_boats_pier | ספור את הסירות הקשורות למזח הצפוני | count/how many + boat + tie/moor + north + pier/dock/jetty/wharf |
| s_lost_uav | אבד קשר עם הכטב"ם, תתחיל סריקה בגזרה הצפונית | lost/no contact + uav/drone/unmanned/aircraft + scan + north + sector/zone/area |
| s_roger_over | רות, ממשיך בסריקה, עבור | roger/copy/acknowledged + continu + scan + over |
| i_orange_cap | עקוב אחרי האדם עם הכובע הכתום | track/follow + person/man + orange + cap/hat |

- Re-run on Gemma (gpu locked 06:32-06:37): ALL 545: 458 PASS / 76 FAIL / 11 REVIEW; route()
  P50 532 ms, P95 1088 ms. Changed verdicts: square FAIL -> PASS, r_dis4 PASS -> FAIL (both by
  the merge rule; J4's drafts propose a flying answer for both). The 19 new: 8 PASS, 11 REVIEW.
- J1 + J4: drafts in the `draft` field of 21 military and 15 commands cases, each marked
  "draft": true; the scorer ignores `draft`. Review tables above (Hebrew in its own cell).
- TR1: four asserts added to test_bypass_answers_only_full_matches (wait 5, wait 2.5, a full
  turn, a full turn counterclockwise); added, not rewritten. TR3: one new routing test (the echo
  guard; nothing flies; the read-back said). TR5: two new routing tests (an empty plan; a text
  reply).
- Mutation checks (each failed 1 test, then restored): the wait rule; the full-turn degrees; the
  echo guard off; the empty-plan check off; a text reply treated as a Gemma failure.
- Checks: flake8 rc 0 (whole tree); pyflakes rc 0; audit "except handlers: 5"; bench/recognizer
  lint clean; suite run 1 "243 passed, 2 skipped", run 2 "243 passed, 2 skipped".
- Change impact:

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| each sentence once; lists by name | the benchmark's counts | totals change (729 -> 545) | none |
| square, r_dis4 expect "none" | their verdicts | by the J5 rule | none |
| scorer: alternatives, "halt", "either way" | only cases that use them (none yet but r_mis5) | additive | none |
| TR1, TR3, TR5 | none in the app | additive | 3 new tests, 1 test extended |

- Y2: confirm.py reads the dataset folder; fixed (skips lists).
- Proposed HISTORY entry: "2026-09-29 -- every recognizer sentence has one home. Why: J2, J5.
  Result: 545 sentences, each once, in 6 topical files; 4 live lists of case names; 19
  sentences that only the spoken lists held were added. Gemma 4 E4B: 458 PASS / 76 FAIL / 11
  REVIEW. The military and open cases have drafts for the owner (J1, J4). Where:
  datasets/recognizer/, bench/recognizer/."
- WAITING: the owner's review of the J1 and J4 drafts, and the rm of datasets/e2e.

### Brief 3 checkpoint (2026-09-30): SC1, the scorer checks the vision kind
- Files: bench/recognizer/scorer.py (score_perception fails another kind when `vision` names
  one); bench/recognizer/test_scorer.py (NEW, 4 tests: the kind, no kind, "+90" and "either
  way", alternatives and a halt); tools/asr-verify-transcript/labels.py (vision_expect saves the
  kind as `vision`, no longer as the first keyword group; vision_of reads it back; the page's
  API is unchanged, so index.html and server.py need no change); test_labels.py and
  test_server.py (REWRITTEN, loudly marked: the SC1 ruling changed the saved format);
  datasets/recognizer/perception.json (138 drafts), military.json (`vision` in the 6 drafted
  vision requests), datasets/asr/recordings.json (14 kinds moved to `vision`, 14 drafts);
  both READMEs.
- Format agreed with the page: a perception expect is {"kind": "perception", "vision":
  "highlight"|"count"|"describe" (absent = any kind), "groups": [target groups]}. labels.py
  reads and writes exactly that.
- Mutation checks (each failed 2-3 tests, then restored): the scorer ignores `vision`; the page
  drops the kind; the page cannot read the kind back.
- Checks: flake8 and pyflakes clean in bench/recognizer, tools/asr-verify-transcript and the
  app; audit "except handlers: 5"; app suite "248 passed, 2 skipped" twice; scorer + labelling
  tests "23 passed" once. The next run showed 1 FAIL in bench's new, unfinished work:
  test_server.py::test_a_removed_clip_keeps_its_reason_and_is_never_graded ("removed" clips).
  bench edited labels.py and test_server.py while I held their locks; my SC1 edits are intact.
  Not my files to fix; bench's next checkpoint decides.
- No benchmark re-run (the brief: only after the owner's review). Nothing counts differently
  until the drafts are confirmed: today no topical case has `vision` in `expect`; the 14
  recordings now grade their kind (path B, not yet built).
- Change impact:

| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| scorer checks `vision` | only cases with `vision` | additive | new test_scorer.py |
| the page saves the kind in `vision` | the recordings file format | yes, by ruling SC1 | 2 tests rewritten (labelling) |
| 14 recordings converted | their saved kind | no: same kind, own field | none |

- Proposed HISTORY entry: "2026-09-30 -- the recognizer benchmark grades the vision kind. Why:
  SC1. Result: a perception case names its kind in `vision`; the scorer fails another kind; the
  labelling page saves the kind there. 144 kinds drafted for the owner's review; 14 recordings
  moved their chosen kind into the field. Where: bench/recognizer/scorer.py,
  tools/asr-verify-transcript/labels.py, datasets/."
- WAITING: the owner's review of the SC1 kinds (and of the J1/J4 drafts), then a re-run.

