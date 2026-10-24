# Step 5, part 1: the public Python names that no rev3 header declares (as built, NOT reviewed)

Made by script on 2026-10-02 from the code: the signature and the first words of the docstring.
Step 7 applies: these may be faithful to the owner's decisions and only missing from the headers.
For each module the owner rules: "write it into its header" or "it should not exist / change it".
Total: 100 names.


## app/chat_rows.py
| name | what its docstring says |
|---|---|
| `chat_kind(text)` | Classify a GENERIC model say() line to its kind. Used ONLY at the say() write site, where the kind is not known structurally; every other write site t |
| `chat_header(session_dir, killed)` | The header: title (Ubuntu), then ONE line per subsystem derived from the live env/config (mono), then the dump path + key hints. Each line follows the |
| `group_turns(chat, thinking)` | Group the flat chat into turns. A turn STARTS at a user line and runs to the next user line. Highlight + describe results land SECONDS later from a wo |
| `turn_rows(turns)` | The pane rows: (tag, value, bgr_color, rtl) per line; None between turns. |

## app/draw.py
| name | what its docstring says |
|---|---|
| `ascii_only(s)` | Drop non-ASCII characters; cv2.putText cannot draw them. |
| `wrap_px(text, maxpx, font)` | Wrap to fit maxpx using the real font metrics (per-element font). PIL path only. A line break in the text starts a new line: PIL cannot measure multi- |
| `draw_box(img, box, color, label, thick)` | (no docstring) |

## app/main.py
| name | what its docstring says |
|---|---|
| `parse_source()` | The one CLI argument: the video source (falls back to config.INPUT). |
| `start_processes(supervisor, log_dir, source, gemma)` | Start every process a configured option needs. -> (every Process handle, the gstreamer handle or None). @gemma: the Gemma client; its server's row tur |

## app/state.py
| name | what its docstring says |
|---|---|
| `class Shared` | (no docstring) |

## app/status_pane.py
| name | what its docstring says |
|---|---|
| `detail_lines(detail)` | The detail, wrapped, at most config.STATUS_DETAIL_LINES lines. |

## app/turns.py
| name | what its docstring says |
|---|---|
| `show_record(rec)` | Show what a turn did in the chat: its kind, its mission steps, its action, and a reject's reason. rec is the session's current record (None or empty:  |
| `say_with(voice)` | -> say(text): one chat line (its kind from chat_kind) and the same text spoken. |

## app/ui.py
| name | what its docstring says |
|---|---|
| `record_frame(perf, t0, t_read, t_draw, t_end, previous_end)` | One "frame" event per frame (owner, C.1: "Record everything"). The times are monotonic seconds: t0 the read starts, t_read the draw starts, t_draw the |
| `source_label(source)` | A short HUD label for the video source. |
| `dji_label()` | A short HUD label for the phone-app target (mock or real). |
| `tint_masks(display, masks)` | Blend every mask onto display in the mask colour. A mask of another size (a frame of another resolution) is scaled to the display first. |
| `draw_overlays(display, boxes, masks, use_masks)` | Draw the mask tint and the highlight boxes onto display. |
| `compose_canvas(display, fps, src_label, dji_text, session_dir, board, manual)` | The camera full width on top; below it the status pane and the chat pane side by side (owner layout 2026-09-22). The HUD and the talk prompt sit on th |
| `on_mouse(event, _x, _y, flags, _param)` | The mouse wheel scrolls the chat: up = older rows, down = back toward the newest. |
| `handle_key(key, on_clear)` | Apply one window key. -> True when the app should quit. c = clear the highlight, t = masks on/off, [ / ] = scroll the chat, x = clear the chat. The ki |

## audio/speech_out.py
| name | what its docstring says |
|---|---|
| `output_class(name)` | Import the output's module (at start, by SpeechOut) and return its class. |

## audio/tts_laptop.py
| name | what its docstring says |
|---|---|
| `LaptopTts.stop_current()` | (no docstring) |

## audio/tts_phone.py
| name | what its docstring says |
|---|---|
| `PhoneTts.stop_current()` | The phone speaks on its own; a newer answer simply follows. |

## dji_app/client.py
| name | what its docstring says |
|---|---|
| `DjiApp.from_env(cls, perf)` | Build from config.DJI_* (derived from CONTROL=mock|real): mock -> 127.0.0.1:8079, not real; real -> PHONE_IP:8080, real (HUMAN-run only). CONTROL is t |
| `mock_ready()` | True once the mock phone app accepts a TCP connection on its port. |

## gemma/server.py
| name | what its docstring says |
|---|---|
| `thinking_flags(enabled)` | Gemma thinking on or off, through the jinja template. OFF needs both flags: --reasoning-budget 0 alone still narrated on 57/413 translations; enable_t |
| `port_up(port)` | True when a llama-server on this port answers /health with 200 (loaded and ready). It answers 503 while the model still loads. |
| `warm_ready(port, warm_up)` | port_up, then ONE warm-up request (owner L1): the first request of a fresh server evaluates the whole planner prompt (1.15 s of a 1.5 s plan); the war |

## log/perf_report.py
| name | what its docstring says |
|---|---|
| `percentile(values, p)` | The p-th percentile (0-100) of a non-empty list, nearest rank. |
| `summarize(rows)` | -> {key: [rows]}; key is the stage, plus its label, kind, output or row. |
| `stats_line(name, values)` | One table row: name, n, min, the percentiles, max (ms, one decimal). |
| `stage_table(rows)` | The stats table: one row per stage group, and one per part of a stage. |
| `gpu_line(rows)` | (no docstring) |
| `slowest_frames(rows, count)` | The `count` frames with the longest gap, slowest first, with their wall time. |

## log/session.py
| name | what its docstring says |
|---|---|
| `SessionLog.begin(heard, source)` | Open this thread's utterance. Only a MIC utterance claims an audio clip: a phone transcript has none, and must not steal the mic's (review R27). The c |
| `SessionLog.current()` | This thread's open utterance record, or None. |
| `SessionLog.cur_seq()` | (no docstring) |
| `SessionLog.det_payload(raw_dets)` | Model-agnostic detection serialization for a pass (conf/box/label). |

## perception2/concept.py
| name | what its docstring says |
|---|---|
| `phrase_concepts(phrase)` | Attribute-PRESERVING concept string for the live highlight path (SCENE_SEG=sam3). Strips only the leading article and fans a bare category word out th |

## perception2/counting.py
| name | what its docstring says |
|---|---|
| `count_instances(dets, thr, contain, frame_area, min_frac)` | dets: [{'conf': float, 'box': (x1,y1,x2,y2)}, ...]. Returns the kept detections (highest conf first). frame_area + min_frac drop specks: real flight 2 |
| `median_count(counts)` | Median of a short list of ints (0 for an empty list); the lower middle for an even length. |

## perception2/dispatcher.py
| name | what its docstring says |
|---|---|
| `Dispatcher.submit(fn, name)` | Hand one task (a no-argument callable) to the dispatcher. -> SUBMIT_OK, or SUBMIT_FULL when max_tasks tasks are already alive or waiting. |

## perception2/engine.py
| name | what its docstring says |
|---|---|
| `scale_vlm_box(box, frame_shape)` | VLM boxes arrive normalized 0-1 or 0-1000 depending on the prompt; auto-detect and return pixel coordinates. |
| `class PerceptionEngine` | detect(frame, phrase, conf) -> (status, hits); hits = [{"label","conf","box"}...] sorted by conf desc. mask_for_box(frame, box) -> bool mask or None.  |
| `PerceptionEngine.apply_masks(frame, dets, use_sam)` | Mask hygiene (mechanism 2). Returns (kept_dets, masks). |
| `PerceptionEngine.highlight_step(frame, target, vlm_box_px, use_sam)` | One frame of highlighting (mechanisms 1-3). Returns (dets, masks, debug). |
| `PerceptionEngine.draw_step(frame, raw, target, vlm_box_px, use_sam)` | What highlight_step draws from detections it already has (the gate's own: owner L2). -> (dets, masks, debug). |
| `PerceptionEngine.presence_gate(frame, phrase)` | Ask the VLM whether the phrase is actually visible (mechanism 3). Returns (present, vlm_box_px|None). A failed Gemma call fails OPEN: the detector's o |

## perception2/sam3_lock.py
| name | what its docstring says |
|---|---|
| `class PriorityLock` | @_waiting: a heap of (priority, arrival) tickets. @_held: True while one thread owns it. |
| `PriorityLock.acquire(priority)` | Block until this caller is the best waiter and the lock is free. No timeout: a forward pass always ends (a GPU error inside it dies the app). |

## perception2/verify.py
| name | what its docstring says |
|---|---|
| `split_target(phrase)` | 'man with glasses talking to woman in yellow shirt' -> head='man with glasses', related=[Related('woman in yellow shirt','yellow')], relation='near'. |
| `rel_holds(relation, a, b)` | Does head box a stand in `relation` to related box b? Plain geometry, tolerant. |
| `region_is_color(frame_bgr, box, color)` | Dominant color of the box's middle, in HSV, against a small name table. |
| `verify_highlight(detect, frame, target, floor, hit_thr, frame_area, min_frac, rel_thr)` | Once per query. detect(frame, phrase, floor) -> (status, hits). Returns a Verified. The head must clear hit_thr (it is what gets drawn). The related n |

## perception2/vision.py
| name | what its docstring says |
|---|---|
| `absent_reason(veto, raw, best)` | Why a highlight was refused, in plain words, for the chat. |

## perception2/vlm_client.py
| name | what its docstring says |
|---|---|
| `ask(gemma, frame_bgr, question, dets)` | Ask Gemma (a gemma.client.Gemma) about the frame. -> (status, reply). status is True on success. reply = (long_text, highlight_target|None, vlm_box|No |
| `parse_reply(txt)` | Split the model's labelled reply into (long, target, box, short). Pure text; testable. |

## recognizer/fast_path.py
| name | what its docstring says |
|---|---|
| `has_duration(text)` | True when the sentence gives a time span ("for 10 seconds"). |
| `bare(text)` | The sentence without punctuation and fillers, single-spaced. |
| `is_clear(text)` | True when the sentence asks to clear the highlight (checked after critical()). |

## recognizer/guards.py
| name | what its docstring says |
|---|---|
| `mission_numbers(mission)` | Every number in a mission's steps, as a magnitude. |
| `numbers_vs_mission(he2, mission)` | The number guard for the direct path: every number spoken in the Hebrew must appear in the mission (magnitude). Returns the list of missing numbers ([ |
| `is_shot_echo(he2, mission)` | True when the plan equals a planner example and the sentence holds none of that example's numbers. The sentence is Hebrew, so its numbers are read the |
| `negation_only(he)` | True iff the utterance is a PURE action-negation: at least one negated action clause and NO clause carrying a positive order. The negation trigger con |

## recognizer/lexicon.py
| name | what its docstring says |
|---|---|
| `find_nouns(he_text)` | Lexicon nouns in the Hebrew text, in order of appearance: [(hebrew, english), ...]. |
| `fix_target(he_text, target_en)` | Returns (target_en, note). note is None when nothing changed. |

## recognizer/numbers.py
| name | what its docstring says |
|---|---|
| `is_number_word(word)` | Digits, a number word, a construct numeral, or a fraction. |
| `is_number_token(token)` | A number token, with or without one front letter (ב-5, ו5, בחמישה, ורבע). Trailing punctuation is ignored. |
| `meter_has_number(before, after)` | Does a מטר between the words `before` and `after` carry its own number? Hebrew puts the number on either side (חמישה מטר / מטר אחד). A number AFTER it |
| `is_bare_meter(toks, i)` | toks[i] is מטר with no number of its own: it means ONE meter. Only מטר: the other unit words are homographs (שנייה = a moment, מעלה = upward). |
| `read_fractions(s)` | Every Hebrew fraction in s -> digits (after hebnum_to_digits, so a count before a fraction is already digits: 3 רבעי סיבוב). |
| `nums_he(s)` | Every number in a Hebrew sentence, digits and composed number words, sorted. A bare singular unit counts as one (מטר = 1, מטר וחצי = 1.5) -- both were |
| `nums_en(s)` | Every number in an English sentence; adjacent number words compose (twenty five, one hundred twenty, two and a half -- mirroring the Hebrew composer's |

## recognizer/parse.py
| name | what its docstring says |
|---|---|
| `recognize_direct(he)` | harden2: the Hebrew front half. Stage 0 the fast path (emergency / manual / auto -> that kind), stage 1 bypass (deterministic missions, no model), the |

## recognizer/prompts.py
| name | what its docstring says |
|---|---|
| `write_prompts_md(path)` | Write PROMPTS.md next to this file (not into the folder it is run from). |

## recognizer/recognizer.py
| name | what its docstring says |
|---|---|
| `reject_why(action)` | The plain reason for a rejection, so the operator can judge whether it was valid (owner 2026-09-12). |
| `Recognizer.observe()` | Add fields (he2, flags, kind, target, action, timings) to this turn's log record. |
| `plan_messages(he2)` | The planner's request: its long system prompt, the example turns, the sentence. |

## recognizer/rewrites.py
| name | what its docstring says |
|---|---|
| `Rule.apply(s)` | (no docstring) |
| `he_word(core, prefixes)` | Canonical Hebrew word boundary: clitic prefixes break \b, so the boundary is a non-Hebrew lookaround on both sides. Hand-rolled (?<![HE])...(?![HE]) p |
| `inline_english(s)` | (no docstring) |
| `add_missing_verb(s)` | (no docstring) |
| `explicit_one_meter(s)` | (no docstring) |
| `register_imperative(s)` | (no docstring) |
| `apply_he(s)` | All of stage 2, in order. Returns the rewritten Hebrew and the names of fired rules. |

## runtime/fatal.py
| name | what its docstring says |
|---|---|
| `asyncio_crash_handler(loop, context)` | For loop.set_exception_handler: an exception escaping an asyncio task is a bug -> die(). |

## runtime/supervisor.py
| name | what its docstring says |
|---|---|
| `class ProcessSpec` | What a module needs started. The module describes it; the app starts it. @ready: a no-argument callable, True once the process can serve (None = ready |
| `Supervisor.up_event(name)` | The Event that is set once `name` is UP the first time. |

## sam3/contract.py
| name | what its docstring says |
|---|---|
| `class VisionBackend` | What the highlight engine needs from a vision model. SAM3 is the one backend today. |

## sam3/loader.py
| name | what its docstring says |
|---|---|
| `class BackendLoader` | Loads the chosen backend on its own thread (the model takes seconds to minutes) and answers for it meanwhile: detect() returns (DETECT_NOT_READY, [])  |

## sam3/model.py
| name | what its docstring says |
|---|---|
| `default_dir(precision, quantize)` | The ready nf4 folder for the app's nf4 load; the bf16 checkpoint for anything else (bf16, fp8, or quantizing it to nf4). |
| `class Sam3Backend` | detect(frame_bgr, phrase, conf) -> (status, hits); hits = [{"label","conf","box"} ...] sorted by conf desc. mask_for_box(frame_bgr, box) -> bool mask  |

## util/boxes.py
| name | what its docstring says |
|---|---|
| `frame_area(frame)` | A frame's area in pixels. |

## util/guarded.py
| name | what its docstring says |
|---|---|
| `file_op(what, fn)` | Run one filesystem step fn(*args). -> True when it worked. A failure prints `what` and the reason, and returns False: the caller decides what it means |
| `stream_call(awaitable)` | Await one asyncio stream call (readline, readexactly, drain). -> (True, result), or (False, the reason) when the peer left (ConnectionError, a short r |

## util/hebrew.py
| name | what its docstring says |
|---|---|
| `split_front(word)` | A number word with one front letter -> (letter, number word). Anything else -> ("", word): a word that is a number word by itself keeps its first lett |

## video/cam_list.py
| name | what its docstring says |
|---|---|
| `show_selected()` | One line for WEBCAM_DEV: its state; "CAPTURE" in it means it gives frames. A camera that gives no frame is read once more after CAMERA_CHECK_RETRY_SEC |
| `show_all()` | (no docstring) |

## video/ros_stream.py
| name | what its docstring says |
|---|---|
| `class RosStream` | The latest frame on camera/stream. read() -> (ok, frame); frames counts NEW frames (a stalled stream still returns its last frame). |
