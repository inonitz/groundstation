# harden2 tests

Every test in this folder, one line each, generated from the code on 2026-09-27
(245 tests). One test file per module; shared helpers live in support.py. How to run them and
the opt-in flags: docs/spec-harden2-run-arguments.md, section 5. When a test is added, removed or
renamed, update this list in the same change.

## test_app.py (40 tests)

Tests for the app module (app/): the global keys' handler and the app assembly and its vision flow (main.py), the screen helpers (ui.py), and the status and chat panes (status_pane.py, chat_pane.py).

- `test_only_function_keys_act_and_letters_never_do` — The app's key handler: F4 toggles manual, F1 quits, F2 clears the highlight; a letter (typed in another window) does nothing, Q included (owner 2026-09-23: "Use
- `test_every_global_key_is_a_distinct_function_key`
- `test_a_highlight_turn_draws_and_logs_it` — changed 2026-09-30 (owner L2): it waits for the tracking pass before the clear.
- `test_a_count_turn_says_the_number`
- `test_sam3_not_ready_is_never_absent_and_keeps_the_highlight` — R22 + R23: while SAM3 loads, a gate or a count says 'not ready' -- never 'absent' or 'counted 0' -- and a live highlight stays.
- `test_an_absent_object_is_said_with_the_reason`
- `test_a_describe_turn_shows_and_speaks_the_short_answer`
- `test_a_mission_turn_flies_and_lists_the_steps`
- `test_a_command_turn_ends_the_e2e_timing_when_the_phone_app_answers` — C2: a scripted transcript starts e2e; the reply to /c/fly ends it; a describe turn records none.
- `test_a_highlight_turn_waits_for_its_first_box_and_a_release_starts_the_timing` — C2: the F5 release starts e2e; a highlight hands it to the screen's first box.
- `test_an_emergency_turn_is_spoken`
- `test_a_phone_transcript_is_recorded_as_phone` — R27: the real SessionLog writes each turn's source in the trace; a phone transcript never takes the mic's clip (TR14).
- `test_a_full_vision_service_closes_the_refused_record`
- `test_a_count_of_zero_says_not_found` — TR6: nothing counted is said ("not found").
- `test_a_highlight_while_sam3_loads_says_not_ready` — TR6: "not ready", nothing drawn, never "absent".
- `test_a_lost_highlight_clears_the_drawing_and_says_so` — TR6: the boxes go, the chat says it, the record closes as given up.
- `test_a_failed_describe_closes_its_record_with_no_chat_line` — TR6: the record closes as failed; no answer line.
- `test_layout_camera_on_top_status_and_chat_below`
- `test_every_frame_is_recorded_with_its_parts_and_the_gap`
- `test_scroll_keys_move_the_chat_and_never_go_below_zero`
- `test_the_c_key_clears_through_the_given_function`
- `test_source_label_for_every_source_kind`
- `test_dji_label_says_mock_or_real`
- `test_draw_overlays_tints_the_mask_only_when_masks_are_on`
- `test_parse_source_reads_the_one_argument`
- `test_mouse_wheel_scrolls_the_chat`
- `test_ascii_only_drops_non_ascii`
- `test_pane_has_the_frame_height_and_the_status_width`
- `test_waiting_is_orange`
- `test_up_is_green_and_any_other_state_is_red`
- `test_a_long_detail_is_cut_and_the_pane_draws_only_the_cut_lines` — TR13: detail_lines cuts to the set lines and characters; the pane from the long detail equals the pane from the cut text, pixel for pixel.
- `test_status_pane_takes_its_width_from_the_caller`
- `test_chat_pane_takes_the_width_it_is_given`
- `test_scrolling_hides_the_newest_rows`
- `test_draw_box_draws_the_box_and_its_label`
- `test_chat_kind_classifies_generic_lines`
- `test_the_settings_decide_which_processes_start`
- `test_the_keyboard_hook_starts_without_the_mic`
- `test_a_line_break_in_a_chat_line_does_not_crash_the_pane` — 2026-09-25: a transcript with a line break crashed PIL's textlength (live run).
- `test_app_end_to_end_over_ros` (opt-in: needs a flag)

## test_audio.py (18 tests)

Tests for audio/: speech in (the ROS mic source's process, the phone source over REAL sockets, SpeechIn) and speech out (the phone voice over a REAL local HTTP server, the laptop voice, SpeechOut).

- `test_asr_argv_is_built_from_config`
- `test_capture_device_and_no_recording`
- `test_extract_drops_a_malformed_line_and_keeps_good_ones`
- `test_real_listener_survives_garbage_drops_and_short_bodies`
- `test_an_over_long_line_ends_only_that_connection` — R12: a line over asyncio's 64 KiB limit ends that connection; the listener keeps serving.
- `test_a_slow_command_does_not_let_the_duplicate_copy_through` — R21 SAFETY: the phone sends each command over REST AND TCP. A slow first command (Gemma planning) must not block the loop so long that the second copy misses th
- `test_the_asr_server_process_is_a_laptop_part`
- `test_speech_in_runs_every_source_and_names_it`
- `test_a_mic_transcript_over_ros_is_one_turn` — TR4: a transcript on the ASR topic (real ROS2) reaches the app once, as "ros"; an empty one gives no turn.
- `test_an_unknown_speech_source_dies`
- `test_the_phone_voice_is_a_request_to_the_phone_app`
- `test_the_phone_voice_speaks_even_in_manual_mode`
- `test_a_dead_phone_app_is_waiting_and_never_kills_the_app` — No answer: the speech fails, the "dji app" row goes WAITING (orange), the app lives.
- `test_speech_out_sends_every_sentence_to_each_output`
- `test_an_unknown_speech_output_dies`
- `test_the_laptop_voice_plays`
- `test_the_laptop_voice_dies_at_once_on_a_playback_error` — Owner ruling 9a-1: no retry; the sound system itself broke.
- `test_phonikud_loads_only_when_the_laptop_speaks` — Owner D13 + Q6: importing the app never loads phonikud; only the "laptop" output does.

## test_control.py (6 tests)

Tests for control/: control executes flight through the REAL phone-app client against a REAL local HTTP server (test/support.py). It owns the one transmit switch.

- `test_manual_stops_then_refuses_every_mission_without_sending_it`
- `test_auto_allows_missions_again`
- `test_the_kill_key_toggles_manual_and_auto`
- `test_emergency_halts_in_auto_and_stops_in_manual`
- `test_manual_refuses_missions_even_when_the_stop_did_not_arrive`
- `test_outcome_text_says_what_really_happened`

## test_dji_app.py (12 tests)

Tests for dji_app/: the phone-app client (status codes, the mock-only guard, every request's path and body, a malformed reply) and the mock under the supervisor. Real HTTP servers, no fakes of the client itself.

- `test_the_mock_process_waits_instead_of_dying`
- `test_a_status_is_the_standard_library_s_http_status`
- `test_the_real_mock_starts_under_the_supervisor_and_answers` — REAL path, mock only (127.0.0.1): the supervisor starts the real mock, the phone app talks HTTP to it.
- `test_loopback_guard_accepts_only_real_loopback_addresses`
- `test_a_malformed_phone_reply_is_a_status_not_an_exception` — R11: a reply that is not valid HTTP (a garbage status line) returns None (no answer); it never throws.
- `test_every_request_posts_its_path_and_body`
- `test_transmit_off_blocks_motion_but_never_the_stop`
- `test_from_env_uses_the_config_target`
- `test_a_command_that_reaches_the_phone_app_ends_the_e2e_timing` — C2: any reply ends e2e once; a blocked command does not.
- `test_a_real_host_without_allow_real_dies`
- `test_the_phone_app_row_goes_up_again_when_the_app_answers` — WAITING while nothing answers; UP once a phone app answers GET /status/ again.
- `test_a_waiting_phone_app_is_checked_every_2_s` — Owner U6 a: UP within about 2 s of the phone app answering; process restarts stay 5 s.

## test_gemma.py (9 tests)

Tests for gemma/: the server's command line and start-up, and the ONE client. The client is tested against a real local HTTP server that speaks the chat-completions shape; no model is loaded.

- `test_argv_is_built_from_config`
- `test_thinking_off_needs_both_flags`
- `test_port_up_is_false_on_a_closed_port`
- `test_the_process_is_one_spec_for_the_app_and_the_benches`
- `test_the_server_row_waits_for_one_warm_up_request` — Owner L1: ready only after /health AND one warm-up request.
- `test_request_returns_true_and_the_text`
- `test_request_returns_false_when_nothing_listens`
- `test_request_returns_false_on_an_http_error`
- `test_a_malformed_reply_is_a_failed_request_not_an_exception`

## test_keys.py (4 tests)

Tests for keys/: the global keys over a REAL ROS2 topic (keys.py).

- `test_a_press_is_reported_once`
- `test_release_and_repeat_are_not_reported`
- `test_keys_reports_every_key_and_knows_nothing_about_the_drone`
- `test_short_message_is_ignored`

## test_log.py (27 tests)

Tests for log/: session.py (the recording). Crash safety (a SIGKILL never leaves a torn file), the trace line per utterance with its audio clip, and the per-request perception dirs with their passes.

- `test_committed_utterances_are_durable_and_complete`
- `test_atomic_json_leaves_no_tmp_and_valid_file` — Owner D6 a: through SessionLog's own writes (a request, a pass, meta.json): whole files, no temp file left.
- `test_perception_pairing_after_clean_request`
- `test_sigkill_mid_session_leaves_no_partial_or_corrupt_file` — Spawn a writer, SIGKILL it mid-flight, then prove the recording is readable: every trace line parses, and every meta/request/pass json parses. A lingering *.tmp
- `test_trace_line_and_causal_clip_claim`
- `test_reject_reason_in_trace` — The recognizer passes the reason (it words its own rejects); the log records it.
- `test_per_request_dir_and_passes`
- `test_begin_request_supersedes_open_one`
- `test_meta_json_is_written_at_start` — R14: the session's meta.json (host, ASR, model, planner) exists after start-up.
- `test_an_uncreatable_session_folder_dies_at_start` — The folder cannot be made: its parent is a plain FILE (this fails for root too).
- `test_a_failed_write_later_means_a_broken_disk_and_dies`
- `test_a_missing_audio_clip_is_skipped_not_fatal`
- `test_end_request_records_verdict_and_passes_without_rereading`
- `test_current_is_per_thread`
- `test_vision_and_describe_requests_never_touch_each_other` — R26: the SAM3 thread and the Gemma thread each have their own open request.
- `test_only_a_mic_utterance_claims_the_audio_clip` — R27: a phone transcript has no audio and must not steal the mic's clip.
- `test_perf_buffers_every_event_and_writes_it_on_close`
- `test_a_mark_moves_and_ends_with_its_fields`
- `test_the_writer_thread_writes_the_buffer_every_period`
- `test_die_writes_the_perf_buffer_before_every_other_cleanup`
- `test_startup_records_each_row_when_it_is_first_up`
- `test_the_gpu_sampler_records_memory_and_load` (skipped without the NVIDIA driver)
- `test_no_perf_records_nothing`
- `test_the_perf_report_gives_percentiles_per_stage`
- `test_the_perf_report_lists_the_slowest_frames`
- `test_the_scripted_run_reads_sentences_and_waits`
- `test_the_scripted_run_refuses_anything_but_the_mock` — SAFETY: with CONTROL=real it dies before it publishes anything.

## test_perception2.py (49 tests)

Tests for perception2/: the engine, the SAM3 priority lock, the dispatcher, the vision service (count / highlight / clear / describe), concepts, counting, verify, and the Gemma vision client. No GPU: the vision-service tests run the REAL service, dispatcher and lock on a stand-in backend (SAM3 itself is GPU-only).

- `test_phrase_concepts_live_path` — Attributes kept, article stripped, category expanded, empty guarded; relational and positional clauses SAM3 cannot use are dropped to the bare noun. (Moved here
- `test_phrase_concepts_drops_relational_clauses_for_sam3`
- `test_concepts_positional_and_synonyms`
- `test_threshold_drops_low_conf`
- `test_part_inside_whole_is_one_instance`
- `test_side_by_side_chairs_both_count`
- `test_zero_area_box_ignored`
- `test_median_count`
- `test_speck_boxes_dropped_with_frame_area`
- `test_relative_gate_and_mask_hygiene` — 0.48 dies next to 0.90; the kept box is tightened to its mask.
- `test_a_garbage_mask_is_dropped_and_the_box_stays`
- `test_a_detector_whiff_falls_back_to_the_vlm_box`
- `test_presence_gate_absent_and_box_scaling` — Absent -> (False, None); present with a 0-1000 box -> pixel coords.
- `test_relative_gate_keeps_near_peers`
- `test_full_frame_box_without_mask_is_dropped`
- `test_box_scaling_both_conventions`
- `test_failed_detect_draws_nothing_and_reports_it`
- `test_split_target_keeps_the_related_clause`
- `test_rel_holds_geometry`
- `test_region_is_color`
- `test_verify_absent_related_noun_refuses`
- `test_verify_draws_when_relation_holds_and_flags_misplaced`
- `test_verify_simple_query_is_untouched`
- `test_failed_sam3_call_is_a_failed_verdict_not_absent`
- `test_vlm_reply_parsing`
- `test_ask_returns_false_and_no_reply_when_gemma_fails`
- `test_ask_parses_a_successful_reply`
- `test_presence_gate_fails_open_when_gemma_fails`
- `test_apply_masks_tightens_to_the_mask_and_drops_garbage`
- `test_the_lock_serves_a_command_before_waiting_refreshes`
- `test_each_task_runs_on_its_own_thread`
- `test_a_sleeping_task_does_not_block_another`
- `test_past_max_tasks_a_submit_is_refused_not_queued`
- `test_count_is_the_median_then_it_highlights_what_it_counted`
- `test_count_while_sam3_loads_is_not_ready_never_zero`
- `test_an_absent_object_is_refused_with_the_reason`
- `test_verify_refuses_a_backpack_held_by_a_child_when_no_child_is_there` — Owner TR2: VERIFY on in the live service; the backpack is found, no child: refused with the reason.
- `test_a_speck_box_is_dropped_at_the_config_floor` — Owner TR7: MIN_BOX_FRAC at its config value; a 2x2 box is dropped, the cars stay.
- `test_gate_vlm_trusts_gemma_alone` — Owner TR16 + O4: GATE=vlm; Gemma's "none" refuses with the reason "Gemma does not see it", Gemma naming it tracks; SAM3 is not asked at the gate.
- `test_gate_either_draws_when_sam3_or_gemma_sees_it` — Owner TR16: GATE=either; SAM3 alone is enough; neither: refused, SAM3's reason.
- `test_a_highlight_tracks_until_cleared_and_its_thread_ends`
- `test_a_highlight_gives_up_when_the_object_leaves`
- `test_a_new_highlight_replaces_the_old_one`
- `test_the_first_box_is_the_gate_s_own_no_second_pass` — Owner L2: the gate's SAM3 pass makes the first drawn update; the refresh detects again.
- `test_sam3_forward_passes_never_overlap`
- `test_past_the_cap_a_request_is_full`
- `test_the_refresh_period_counts_from_the_start_of_each_detect` — Period 0.2 s, one detect 0.08 s: starts come 0.2 s apart, not 0.28 s.
- `test_describe_answers_through_its_callback`
- `test_every_forward_pass_is_reported_with_its_task`

## test_recognizer.py (50 tests)

Tests for recognizer/: the parser (fast path, bypass, rewrites, numbers, guards) and the Recognizer's routing. No model server is started: PlannerStub answers the plan.

- `test_every_rule_against_its_own_evidence` — Each rewrite rule: every negative untouched, every positive changed.
- `test_hebrew_numbers_become_digits`
- `test_inline_english_words`
- `test_number_guard_reads_hebrew_numbers`
- `test_number_guard_reads_english_numbers`
- `test_bypass_answers_only_full_matches` — includes the wait and the full-turn rules (TR1).
- `test_missing_verb_is_added_to_a_bare_direction`
- `test_a_bare_meter_becomes_one_meter_evidence`
- `test_a_number_after_meter_that_starts_with_and_is_the_next_item` — מטר וחמישה מטר = a meter, and five meters: the first מטר is bare (one meter). A ו-number BEFORE מטר is its count; וחצי after it is its half (owner 2026-09-24).
- `test_emergency_word_stops_and_a_command_does_not`
- `test_emergency_words_2026_09_08_owner_ruling`
- `test_register_rewrites_2026_09_08_owner_ruling`
- `test_pure_negations_refuse`
- `test_real_orders_pass_through_zero_false_fires`
- `test_recognize_direct_routes_pure_negation_to_reject`
- `test_fast_path_english`
- `test_fast_path_hebrew`
- `test_everything_else_is_not_critical`
- `test_direct_mission_flies_when_numbers_match`
- `test_direct_number_guard_rejects`
- `test_direct_highlight_count_describe_reject`
- `test_direct_bypass_and_the_fast_path_skip_the_model`
- `test_spoken_manual_and_auto_go_to_control`
- `test_new_action_verbs_pass_through_to_fly`
- `test_manual_mode_refuses_flight_but_perception_answers`
- `test_failed_gemma_call_is_not_blamed_on_the_user`
- `test_an_emergency_that_did_not_arrive_says_so` — The phone app does not answer: the emergency is reported as NOT reaching the aircraft.
- `test_a_phone_error_status_is_not_reported_as_flown` — R13: a 400/500 from the phone is a FAILED mission, not a flight. Real phone, real codes.
- `test_apply_he_reports_which_rules_fired`
- `test_a_bare_meter_becomes_one_meter`
- `test_number_guard_lists_every_missing_number`
- `test_a_copied_few_shot_example_is_an_echo`
- `test_a_spoken_clear_clears_without_the_model`
- `test_a_full_vision_service_is_said_not_silent`
- `test_clear_miss_is_replaced`
- `test_correct_target_untouched`
- `test_no_lexicon_noun_untouched`
- `test_prefixes_and_order`
- `test_reject_why_names_every_reject_reason`
- `test_a_reject_tells_the_log_why`
- `test_route_decides_and_sends_nothing` — route() only decides: nothing reaches the phone app or the vision service; act() then carries the decision out.
- `test_a_number_with_any_of_the_seven_front_letters_is_read` — the number guard reads a number word with any of the seven front letters (owner Q8).
- `test_the_article_on_a_number_is_a_count_only_before_a_unit`
- `test_two_units_in_a_row_are_two_numbers`
- `test_the_fractions_are_read` — a half, a quarter, a third, an eighth: after a number, alone, and of a turn (owner C.3).
- `test_the_number_guard_matches_a_third_within_a_hundredth`
- `test_a_plan_equal_to_a_few_shot_example_is_refused_and_nothing_flies` — TR3: the echo guard refuses a copied example at routing; the read-back is said; nothing flies.
- `test_an_empty_plan_flies_nothing_and_says_nothing` — TR5.
- `test_a_reply_that_is_not_json_is_a_reject_read_back` — TR5: a text reply is a reject, not a Gemma failure.
- `test_the_warm_up_is_one_plan_request_that_sends_nothing` — Owner L1: the warm-up is the planner's own request for a fixed sentence.

## test_sam3.py (6 tests)

Tests for sam3/: the loader service, the dedup of nested boxes on real SAM3 boxes (CPU), and the real SAM3 model (GPU, opt-in).

- `test_the_backend_loader_is_not_ready_until_loaded`
- `test_the_loader_warms_the_model_up_before_its_row_is_up` — Owner L1: one pass on a blank camera-size frame; the row turns UP after it.
- `test_an_unknown_vision_backend_dies` — An unknown SCENE_SEG -> die() (a hard crash, not an exception), in a child.
- `test_real_sam3_detects_and_masks_a_window` (opt-in: needs a flag) — The real backend on a real picture: detect finds windows, and mask_for_box returns the frame-sized mask it cached. (Moved here from sam3_backend._smoke 2026-09-
- `test_real_deduplicated_boxes_come_back_unchanged` — Owner TR17: real SAM3 boxes from 2026-09-25 runs (CPU): a second dedup returns them unchanged.
- `test_a_real_box_and_a_copy_of_its_inner_part_become_one_box` — Owner TR17: a nested copy of a real box, scored lower, is dropped.

## test_runtime.py (18 tests)

Tests for runtime/: the status board and the generic process supervisor.

- `test_the_board_asks_each_source_in_source_order`
- `test_a_status_starts_starting_and_keeps_its_detail`
- `test_sets_from_many_threads_leave_one_consistent_row`
- `test_die_runs_cleanups_before_exit`
- `test_a_healthy_process_goes_up_and_stops_down`
- `test_ready_probe_holds_starting_until_ready`
- `test_a_dead_process_is_restarted_and_recovers`
- `test_never_ready_counts_as_a_failure`
- `test_gives_up_after_max_restarts_and_dies_with_the_reason`
- `test_a_process_that_is_not_required_waits_instead_of_dying` — Past the budget, a process that depends on the phone app goes WAITING (orange) and is retried; the app does NOT die. When it runs again, it goes UP.
- `test_die_stops_the_children_first`
- `test_a_deliberate_restart_does_not_spend_the_crash_budget`
- `test_a_stable_run_earns_the_crash_budget_back` — TR9: a crash after a stable run starts again with a full budget.
- `test_restart_of_an_unknown_process_is_false`
- `test_an_uncaught_thread_exception_dies_loudly_and_cleans_up`
- `test_no_launch_after_stop_all` — R16: once stopping, _launch starts nothing, so stop_all can never miss a child.
- `test_die_reaches_exit_even_when_a_cleanup_fails_and_runs_once` — R17: a failing cleanup is reported and the rest still run; two threads dying exit once.
- `test_a_missing_package_dies_with_its_install_command`

## test_util.py (4 tests)

Tests for util/: the shared standalone helpers (Hebrew numbers, the port probe, the native-program environment).

- `test_hebrew_number_words_become_digits`
- `test_port_open_sees_a_listener_and_nothing_else`
- `test_native_env_adds_the_native_library_folder`
- `test_boxes_overlap_math` — The one home of the box overlap math: exact values, not just "overlaps".

## test_video.py (7 tests)

Tests for video/: the source classifier, the gstreamer process, Video over a REAL video file (written with OpenCV), and the ROS stream + stall guard over a REAL ROS2 topic.

- `test_source_kind_names_every_source`
- `test_the_gstreamer_process_waits_instead_of_dying`
- `test_a_file_opens_reads_and_hands_out_copies`
- `test_a_source_that_never_opens_dies_with_the_reason`
- `test_ros_frames_arrive_and_the_row_goes_up`
- `test_a_stalled_stream_restarts_gstreamer`
- `test_the_preflight_reads_the_camera_again_before_it_fails` — Owner O3 a: no frame -> one more read after CAMERA_CHECK_RETRY_SECONDS; a good first read does not wait.
