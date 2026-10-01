# harden2 test review (task E3, 2026-09-28)

For each module, this review lists its purpose, the behaviours a user or another module relies on, and the test that proves each one.
It is a report only: no code and no test changed. The ranked findings and a decision table for the owner come at the end.
Method: owner rulings R6, Q7 and U4 a. Coverage was used only to find code that never runs.

| section | content |
|---|---|
| How the suite was read | the coverage run and its limits |
| One section per module | app, keys, audio, video, perception2, recognizer, gemma, dji_app, control, log, runtime, util, config |
| Findings, ranked | behaviours with no test, then tests that prove little, then gaps |
| Decisions for the owner | one ID per finding, the options, the recommendation first |

## How the suite was read
- Tests: every file in test/ (230 tests, 2 skipped without a flag or a GPU). I read each test and checked what its asserts can catch.
- Coverage: one run of the default suite under `coverage run --branch` (230 passed, 2 skipped, under the suite lock). The opt-in whole-app test did not run.
- Limit: coverage sees only the pytest process. Code that a test runs in a child process shows as never run: every die() path, runtime/deps.check, and the whole-app test. Those paths are tested; the review names each one.
- Verdicts: **proved** (a real path; a failing assert is possible), **stand-in** (a stand-in replaces a part that needs the GPU or hardware; accepted), **weak** (the test checks less than its name says, or checks a constant), **none** (no test).

## app (app/)
Purpose: the app itself. main.py builds the services, then the modules, runs the screen, and shuts down in reverse. turns.py turns one sentence and the vision results into chat, speech and the log. ui.py and the panes draw the screen.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Only F1, F2 and F4 act; typed letters never act | test_only_function_keys_act_and_letters_never_do | proved |
| 2 | The global keys are distinct function keys | test_every_global_key_is_a_distinct_function_key | weak: asserts config constants |
| 3 | A highlight turn draws the boxes, and clearing ends it | test_a_highlight_turn_draws_and_logs_it | proved (stand-in SAM3) |
| 4 | A count turn says the number | test_a_count_turn_says_the_number | proved |
| 5 | A count of zero says "not found" | none (the zero branch of turns.on_count never runs) | none |
| 6 | While SAM3 loads, a count says "not ready", never zero | test_sam3_not_ready_is_never_absent_and_keeps_the_highlight | proved |
| 7 | While SAM3 loads, a highlight says "not ready" | none (the NOT_READY branch of on_highlight never runs) | none |
| 8 | An absent object is said with its reason | test_an_absent_object_is_said_with_the_reason | proved |
| 9 | A lost highlight clears the drawing and says so | none at app level (vision level: test_a_highlight_gives_up_when_the_object_leaves) | none |
| 10 | A describe turn shows the long answer and speaks the short one | test_a_describe_turn_shows_and_speaks_the_short_answer | proved |
| 11 | A failed describe (Gemma failed) closes its record, with no chat line | none | none |
| 12 | A mission turn flies and lists the steps | test_a_mission_turn_flies_and_lists_the_steps | proved |
| 13 | An emergency is sent and spoken | test_an_emergency_turn_is_spoken | proved |
| 14 | The e2e timing: a transcript or the F5 release starts it; the phone app's reply or the first box ends it | test_a_command_turn_ends_the_e2e_timing_..., test_a_highlight_turn_waits_for_its_first_box_... | proved |
| 15 | A phone transcript is logged as "phone" | test_a_phone_transcript_is_recorded_as_phone | weak: replaces SessionLog.begin, which is cheap to run for real |
| 16 | A full vision service refuses, and the refusal is logged | test_a_full_vision_service_closes_the_refused_record | proved |
| 17 | The speech function writes a chat line and speaks it (say_with) | none: every test passes its own say() | none |
| 18 | The settings decide which processes start | test_the_settings_decide_which_processes_start, test_the_keyboard_hook_starts_without_the_mic | proved |
| 19 | The layout: camera on top, status and chat below | test_layout_camera_on_top_status_and_chat_below | proved |
| 20 | Every frame is recorded with read, draw, show and the gap | test_every_frame_is_recorded_with_its_parts_and_the_gap | proved |
| 21 | Window keys: c clears, [ and ] scroll, the wheel scrolls | test_the_c_key_..., test_scroll_keys_..., test_mouse_wheel_scrolls_the_chat | proved |
| 22 | Window keys: q or Esc quits, t toggles masks, x clears the chat | none | none |
| 23 | The status pane: UP green, WAITING orange, the rest red | test_waiting_is_orange, test_up_is_green_and_any_other_state_is_red | proved |
| 24 | Long details and many rows never overflow the pane | test_long_detail_and_many_rows_never_overflow | weak: asserts only the shape, so it proves "no crash" |
| 25 | The chat pane scrolls and clamps; a line break does not crash it | test_scrolling_hides_the_newest_rows, test_a_line_break_in_a_chat_line_... | proved |
| 26 | The app starts every module in order, shows the screen, and shuts down in reverse | test_app_end_to_end_over_ros (opt-in, GPU) | opt-in only: main(), Services and UI.run never run in the default suite |
| 27 | An unknown vision backend dies | test_an_unknown_vision_backend_dies | proved (child) |

## keys (keys/)
Purpose: the global keys. The keyboard hook sends every key over ROS2; Keys reports each press once, and each release to the app.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | A press is reported once; auto-repeat is not | test_a_press_is_reported_once, test_release_and_repeat_are_not_reported | proved (real ROS2) |
| 2 | Every key is reported; keys knows nothing of the drone | test_keys_reports_every_key_and_knows_nothing_about_the_drone | proved |
| 3 | A short message is ignored | test_short_message_is_ignored | proved |
| 4 | A release reaches on_release (the F5 release that starts the e2e timing) | none: the app test calls on_key_release directly | none |

## audio (audio/)
Purpose: speech in (the laptop mic through our ASR server, the phone's speech) and speech out (the phone voice, the laptop voice).

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | The ASR server's command line comes from config | test_asr_argv_is_built_from_config, test_capture_device_and_no_recording | proved |
| 2 | The clips land where the session log reads them | test_clips_land_where_the_session_log_reads_them | weak: asserts the folder name of a config constant |
| 3 | A mic transcript on the ASR topic reaches the recognizer (RosAsr) | none in the default suite (the opt-in whole-app test publishes on it) | none |
| 4 | The phone listener survives garbage, short bodies and over-long lines | test_real_listener_survives_..., test_an_over_long_line_ends_only_that_connection | proved (real sockets) |
| 5 | A slow command does not let its REST or TCP duplicate through (safety) | test_a_slow_command_does_not_let_the_duplicate_copy_through | proved |
| 6 | SpeechIn runs every source and names it | test_speech_in_runs_every_source_and_names_it | proved (phone source only) |
| 7 | An unknown source or output dies | test_an_unknown_speech_source_dies, test_an_unknown_speech_output_dies | proved (child) |
| 8 | The phone voice is a /tts request, also in manual mode | test_the_phone_voice_is_a_request_..., test_the_phone_voice_speaks_even_in_manual_mode | proved |
| 9 | A dead phone app: speech fails, the row goes WAITING, the app lives | test_a_dead_phone_app_is_waiting_and_never_kills_the_app | proved |
| 10 | SpeechOut sends every sentence to each output | test_speech_out_sends_every_sentence_to_each_output | proved (phone output only) |
| 11 | The laptop voice plays; a playback error dies at once | test_the_laptop_voice_plays, test_the_laptop_voice_dies_at_once_... | stand-in: the model calls and the sound device are replaced; the real voice never loads |
| 12 | phonikud loads only for the laptop voice | test_phonikud_loads_only_when_the_laptop_speaks | proved |

## video (video/)
Purpose: one video source for the app (webcam, file, stream, or the phone's video over ROS2). It opens, retries, reports its row, hands out frames, and restarts a stalled stream.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Every source string gets its kind | test_source_kind_names_every_source | proved |
| 2 | A file opens, reads, and hands out private copies | test_a_file_opens_reads_and_hands_out_copies | proved |
| 3 | A source that never opens dies with the reason | test_a_source_that_never_opens_dies_with_the_reason | proved (child) |
| 4 | The webcam opens in MJPG at the configured size | none (the webcam branch of _open never runs) | none; needs a camera |
| 5 | A source that opens late is retried until OPEN_TIMEOUT | none (the retry loop never runs) | none |
| 6 | ROS frames arrive and the row goes UP; a stall restarts gstreamer once per window | test_ros_frames_arrive_..., test_a_stalled_stream_restarts_gstreamer | proved (real ROS2); the gstreamer handle is a stand-in |
| 7 | The gstreamer process waits instead of dying | test_the_gstreamer_process_waits_instead_of_dying | proved (the spec only) |
| 8 | The preflight probes only the selected camera (cam_list.py) | none (cam_list.py never runs) | none |

## perception2 (perception2/)
Purpose: the vision system. The vision service runs count, highlight and describe, one thread per task, with one SAM3 forward at a time. It uses the SAM3 backend, the engine, concepts, counting, verify and the Gemma vision prompt.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | A phrase becomes bare SAM3 concepts, with synonyms | test_phrase_concepts_live_path, test_phrase_concepts_drops_relational_..., test_concepts_positional_and_synonyms | proved |
| 2 | Counting: the threshold, a part inside a whole, specks, the median | six counting tests | proved |
| 3 | The engine: the relative gate, mask hygiene, the VLM box fallback, box scaling | test_relative_gate_..., test_a_garbage_mask_..., test_a_detector_whiff_..., test_box_scaling_... | proved |
| 4 | verify: split the target, geometry relations, colour | test_split_target_..., test_rel_holds_geometry, test_region_is_color, three verify tests | proved (as functions) |
| 5 | The live service refuses a highlight whose related noun fails verify (VERIFY=on is the default) | none: the service tests set VERIFY=off, so _gate never calls verify | none |
| 6 | The live highlight drops specks under MIN_BOX_FRAC (0.001 by default) | none: the service tests set MIN_BOX_FRAC=0, so _drop_specks never runs | none |
| 7 | The Gemma vision client: parse, fail, succeed | test_vlm_reply_parsing, test_ask_returns_false_..., test_ask_parses_a_successful_reply | proved (Gemma stand-in) |
| 8 | The SAM3 priority lock serves a command before waiting refreshes | test_the_lock_serves_a_command_before_waiting_refreshes | proved |
| 9 | The dispatcher: one thread per task; past the cap it refuses | three dispatcher tests | proved |
| 10 | Count, highlight, replace, clear, give up, the cap, the refresh period | eleven vision-service tests | stand-in SAM3 (accepted: GPU) |
| 11 | A failed describe is reported as failed | none (the not-ok branch of _describe_task never runs) | none |
| 12 | No video frame yet: the gate says so; the tracker waits | none | none |
| 13 | GATE=vlm and GATE=either (modes that are not the default) | none: only GATE=sam3 runs | none; code for a mode nobody uses |
| 14 | The loader answers "not ready" until loaded | test_the_backend_loader_is_not_ready_until_loaded | proved |
| 15 | SAM3 detects and masks; its nested boxes collapse to one per object (_dedup_overlaps) | test_real_sam3_detects_and_masks_a_window (opt-in, GPU) | opt-in only; _dedup_overlaps is plain Python and never runs in the default suite |
| 16 | The service hands the backend's masks to the screen | none: StandInBackend.mask_for_box always returns None | none at service level (engine level: test_apply_masks_...) |

## recognizer (recognizer/)
Purpose: turns one sentence into a decision. The parser answers on its own first: the emergency words, manual and auto, the bypass, the negation guard. ONE Gemma call plans the rest; the number and echo guards judge the plan; act() carries it out.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Every Hebrew rewrite rule: its positives change, its negatives stay | test_every_rule_against_its_own_evidence, the register and verb tests | proved |
| 2 | Hebrew numbers, fractions and the seven front letters are read | the number tests (test_hebrew_numbers_..., test_number_guard_*, test_the_fractions_are_read, ...) | proved |
| 3 | Emergency, manual and auto answer without the model | test_emergency_word_..., test_fast_path_*, test_spoken_manual_and_auto_go_to_control | proved |
| 4 | The bypass flies a full-match sentence without the model (takeoff, land, spin, turn, move) | test_bypass_answers_only_full_matches, test_direct_bypass_and_the_fast_path_skip_the_model | proved for these five |
| 5 | The bypass: "wait N seconds" and "a full turn" | none (_build_delay and _build_full_turn never run) | none |
| 6 | Pure negations refuse; real orders pass | test_pure_negations_refuse, test_real_orders_pass_through_zero_false_fires | proved |
| 7 | A planned mission flies only when its numbers match | test_direct_mission_flies_when_numbers_match, test_direct_number_guard_rejects | proved |
| 8 | A mission that copies a few-shot example is refused (the echo guard) | test_a_copied_few_shot_example_is_an_echo (the function only) | none at routing level: the "reject-planner-echo" branch of _decide_mission never runs |
| 9 | A plan with no steps is "planned-empty", not a flight | none | none |
| 10 | A reply that is text, not JSON, is a reject | none (that line of plan() never runs) | none |
| 11 | Gemma's English target is checked against the Hebrew nouns | test_clear_miss_is_replaced and three lexicon tests (the function) | proved as a function; the routing note never runs |
| 12 | Manual mode refuses flight; perception still answers | test_manual_mode_refuses_flight_but_perception_answers | proved |
| 13 | A failed Gemma call is not blamed on the user | test_failed_gemma_call_is_not_blamed_on_the_user | proved |
| 14 | An emergency or a flight the phone did not accept is reported so | test_an_emergency_that_did_not_arrive_says_so, test_a_phone_error_status_is_not_reported_as_flown | proved (real HTTP) |
| 15 | route() decides and sends nothing; act() carries it out | test_route_decides_and_sends_nothing | proved |
| 16 | A reject tells the log why | test_reject_why_names_every_reject_reason, test_a_reject_tells_the_log_why | proved |
| 17 | The plan comes from the real Gemma | PlannerStub everywhere; the real model only in the opt-in whole-app test and bench/recognizer | stand-in (accepted: GPU) |

## gemma (gemma/)
Purpose: a service. It keeps the one Gemma server alive and gives one client: request returns (True, text) or (False, "").

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | The command line comes from config; thinking off needs both flags | test_argv_is_built_from_config, test_thinking_off_needs_both_flags | proved |
| 2 | One process spec for the app and the benches | test_the_process_is_one_spec_for_the_app_and_the_benches | proved |
| 3 | port_up is false on a closed port | test_port_up_is_false_on_a_closed_port | proved |
| 4 | request returns the text; False on no server, an HTTP error or a malformed reply | four client tests over a real local HTTP server | proved |
| 5 | The real llama-server starts, answers and restarts | the opt-in whole-app test only | opt-in only (GPU) |

## dji_app (dji_app/)
Purpose: the phone-app client, a service. Every command is an HTTP request. It is loopback-guarded, holds the transmit switch, and owns the "dji app" row.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | A non-loopback host dies without allow_real (safety) | test_a_real_host_without_allow_real_dies, test_loopback_guard_accepts_only_real_loopback_addresses | proved |
| 2 | Every request posts its path and body | test_every_request_posts_its_path_and_body | proved |
| 3 | Transmit off blocks motion, never the stop | test_transmit_off_blocks_motion_but_never_the_stop | proved |
| 4 | A malformed reply is a status, not an exception | test_a_malformed_phone_reply_is_a_status_not_an_exception | proved |
| 5 | The row: WAITING while nothing answers, UP within 2 s once it answers | test_the_phone_app_row_goes_up_again_..., test_a_waiting_phone_app_is_checked_every_2_s | proved |
| 6 | The real mock starts under the supervisor and answers | test_the_real_mock_starts_under_the_supervisor_and_answers | proved |
| 7 | A command that reaches the phone app ends the e2e timing | test_a_command_that_reaches_the_phone_app_ends_the_e2e_timing | proved |
| 8 | from_env uses the config target | test_from_env_uses_the_config_target | weak: copies two config values |

## control (control/)
Purpose: executes flight (the critical commands and missions). It is the only user of the transmit switch.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Manual stops, then refuses every mission without sending it | test_manual_stops_then_refuses_... | proved |
| 2 | Manual refuses missions even when the stop did not arrive | test_manual_refuses_missions_even_when_the_stop_did_not_arrive | proved |
| 3 | Auto allows missions again; the kill key toggles | test_auto_allows_missions_again, test_the_kill_key_toggles_manual_and_auto | proved |
| 4 | An emergency halts in auto and stops in manual | test_emergency_halts_in_auto_and_stops_in_manual | proved |
| 5 | The outcome text says what really happened | test_outcome_text_says_what_really_happened | proved |

## log (log/)
Purpose: a service. The session record (SessionLog) with its atomic disk writes, the perf record, and the read-only tools (show, perf_report).

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Committed utterances are durable; a SIGKILL leaves no torn file | test_committed_utterances_..., test_sigkill_mid_session_... | proved |
| 2 | Atomic JSON, per-request folders and passes, supersede, per-thread requests | seven session tests | proved |
| 3 | The trace line, its audio clip, the reject reason; only a mic utterance claims a clip | four trace tests | proved |
| 4 | A clip whose claim fails keeps the utterance | none (the rename-failure branch never runs) | none |
| 5 | An uncreatable folder or a later failed write dies | two die tests | proved (child) |
| 6 | Perf: every event buffered, the writer thread, marks, die writes first, startup rows, GPU samples | seven perf tests | proved (the GPU test is skipped without the driver) |
| 7 | The perf report: percentiles per stage, the 20 slowest frames | two report tests | proved (the functions); main() of `run.sh perf` never runs |
| 8 | `run.sh show` prints a session (show.py, session_files.py) | none | none |
| 9 | log/score.py (the old list scorer) | none; nothing calls it | dead code: task B1 said to delete it |
| 10 | The scripted run reads its script and refuses anything but the mock | test_the_scripted_run_reads_sentences_and_waits, test_the_scripted_run_refuses_anything_but_the_mock | proved; the tests live in test_log.py, the code in test/scripted_e2e_run.py |

## runtime (runtime/)
Purpose: a service. die() and the crash hooks, the Status rows and the board, the process supervisor, the package check, the ROS spinner.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | The board asks each source in order; a Status is thread-safe | test_the_board_asks_each_source_in_source_order, test_sets_from_many_threads_... | proved |
| 2 | There is no global board | test_there_is_no_global_board_and_states_are_distinct | weak: a hasattr check and five distinct constants |
| 3 | die runs the cleanups once, even when one fails, and stops the children first | three die tests | proved (child) |
| 4 | An uncaught thread exception dies loudly | test_an_uncaught_thread_exception_dies_loudly_and_cleans_up | proved (child) |
| 5 | The supervisor: UP, the ready probe, restart, never ready, give up and die, WAITING for phone parts, deliberate restarts | nine supervisor tests | proved |
| 6 | The crash budget resets after a stable run (stable_s) | none (the reset line never runs) | none |
| 7 | A missing package or file dies with its install command | test_a_missing_package_dies_with_its_install_command | proved (child); main() of `run.sh preflight` never runs |

## util (util/)
Purpose: small shared helpers: the guarded third-party calls, Hebrew numbers, the port probe, the native-program environment.

| # | behaviour | test | verdict |
|---|---|---|---|
| 1 | Hebrew number words become digits | test_hebrew_number_words_become_digits (and the recognizer's number tests) | proved |
| 2 | port_open sees a listener and nothing else | test_port_open_sees_a_listener_and_nothing_else | proved |
| 3 | native_env puts the native library folder first | test_native_env_adds_the_native_library_folder | proved |
| 4 | guarded.py turns HTTP, JSON, file and stream errors into statuses | through the gemma, dji_app, audio and log tests | proved (no own test; the error branch of file_op runs only in a child) |

## config (config/)
Purpose: the one source of every value. The owner ruled that config has no tests of its own. Several tests above assert config constants (app 2, audio 2, dji_app 8, the 2 s check). They guard against a typo, not a behaviour.

## Findings, ranked

### A. Behaviours with no test
1. **The bypass: "wait N seconds" and "a full turn" (recognizer 5).** These two patterns fly without the model. No test runs them.
2. **The live service never runs verify (perception2 5).** VERIFY=on is the default, but every service test sets it off. The functions are tested; their use in the gate is not.
3. **The echo guard at routing level (recognizer 8).** is_shot_echo is tested; the branch that refuses the mission is not. A break there would fly a copied example.
4. **A mic transcript reaches the recognizer (audio 3).** RosAsr is the laptop's main input. Only the opt-in whole-app test runs it. A real ROS2 test is cheap, like the keys tests.
5. **An empty plan and a non-JSON reply (recognizer 9, 10).**
6. **App turns: a count of zero, a highlight while SAM3 loads, a lost highlight, a failed describe (app 5, 7, 9, 11; perception2 11).**
7. **The speck floor during tracking (perception2 6).** The tests set MIN_BOX_FRAC=0, so the default 0.001 never filters.
8. **The F5 release over ROS2 (keys 4).**
9. **The supervisor's crash-budget reset after a stable run (runtime 6).**
10. **The start and the shutdown order (app 26).** main(), Services and the screen loop run only in the opt-in whole-app test.
11. **The backend's masks on their way to the screen (perception2 16).**
12. **Small or hardware-bound paths:** the window keys q, Esc, t and x (app 22); the webcam branch and the open retry (video 4, 5); the tools `run.sh show`, the main() of `run.sh perf` and `run.sh preflight`, and cam_list.py (log 8, log 7, runtime 7, video 8).

### B. Tests that prove little
1. **Assertions on config constants:** test_every_global_key_is_a_distinct_function_key, test_clips_land_where_the_session_log_reads_them, test_from_env_uses_the_config_target, and the first two lines of test_a_waiting_phone_app_is_checked_every_2_s. They cannot catch a behaviour change, only an edited value.
2. **test_there_is_no_global_board_and_states_are_distinct:** a structure check.
3. **test_long_detail_and_many_rows_never_overflow:** it asserts only the shape, which render_status always returns. It proves "no crash", not "no overflow".
4. **test_a_phone_transcript_is_recorded_as_phone:** it replaces SessionLog.begin, but the real SessionLog is cheap. Reading the trace line would prove the real path.
5. **The laptop voice tests:** the model calls and the sound device are replaced. The real voice never loads in any test.

### C. Gaps: code that no test runs
1. **log/score.py (261 lines):** nothing calls it. Task B1 said to delete it.
2. **GATE=vlm and GATE=either (perception2 13):** code for modes nobody runs.
3. **perception2/sam3_backend.py:** only the opt-in GPU test runs it. `_dedup_overlaps` is plain Python and could be tested without the GPU.
4. **recognizer/prompts.write_prompts_md:** a doc generator, run by hand.
5. **close() methods that never run** (control, gemma, the backend loader, the session, the ROS spinner's stop): each is empty or one line; nothing to test.

## Decisions for the owner
The recommendation is option a in every row. The IDs are TR1-TR17: T1-T9 already exist in the decision ledger (docs/spec-harden2-cleanup.md).

| ID | finding | options |
|---|---|---|
| TR1 | the bypass "wait" and "full turn" are untested (A1) | a) add both to test_bypass_answers_only_full_matches. b) leave them |
| TR2 | verify never runs in the live service (A2) | a) one service test with VERIFY=on: a failing related noun is refused with the reason. b) leave it |
| TR3 | the echo refusal never runs at routing level (A3) | a) one routing test: a plan equal to a few-shot example is refused, and nothing flies. b) leave it |
| TR4 | the mic transcript path has no default test (A4) | a) one test over a real ROS2 topic, like the keys tests. b) rely on the opt-in whole-app test |
| TR5 | an empty plan and a non-JSON reply (A5) | a) two routing tests with PlannerStub. b) leave them |
| TR6 | app turns: a count of zero, a highlight not ready, lost, a failed describe (A6) | a) four short tests on the existing _app fixture. b) leave them |
| TR7 | the speck floor during tracking (A7) | a) one service test with MIN_BOX_FRAC above 0. b) leave it |
| TR8 | the F5 release over ROS2 (A8) | a) extend a keys test to a release. b) leave it |
| TR9 | the crash-budget reset (A9) | a) one supervisor test with a short stable_s. b) leave it |
| TR10 | the start and shutdown order only in the opt-in test (A10) | a) keep it opt-in (it needs the GPU) and run it before each commit. b) build a default-suite start with stand-ins |
| TR11 | the window keys, the webcam, the tools (A12) | a) leave them: small, or needing hardware. b) add tests |
| TR12 | tests that check constants or structure (B1, B2) | a) keep them, marked as config guards. b) delete them |
| TR13 | the shape-only overflow test (B3) | a) assert that the text stays inside the pane. b) rename it to say "does not crash" |
| TR14 | the stand-in in the phone-transcript test (B4) | a) use the real SessionLog and read the trace line. b) leave it |
| TR15 | log/score.py (C1) | a) delete it, as task B1 said (`run.sh score` is already gone); it is already in the owner's rm command of 2026-09-28. b) keep it |
| TR16 | GATE=vlm and GATE=either (C2) | a) delete the two modes (YAGNI). b) test them. c) leave them |
| TR17 | _dedup_overlaps (C3) | a) one CPU test of the nested-box collapse. b) leave it to the opt-in GPU test |

Owner rulings (decision ledger): TR1, TR2, TR3, TR4, TR5, TR6, TR7, TR9, TR10, TR12 (keep 1, 3, 5; delete 2 and 4), TR13, TR14, TR15, TR16 (b: test the modes), TR17: done; TR8 and TR11: no test.
