# Repo churn heatmap (2026-09-01)

Source: `git log --name-status` on feature-hardening-mvd (full history, no renames).
Caveat: git sees EDITS, not executions. "Created once, never touched again" is the
slop signature; high churn over a long span is the real-tool signature.

## Hotspots — top 40 by commit count (the real tools)

| touches | span(d) | idle(d) | file |
|--:|--:|--:|---|
| 36 | 25 | 1 | docs/NOTES.md |
| 27 | 80 | 13 | CMakeLists.txt |
| 25 | 20 | 6 | docs/ROADMAP.md |
| 25 | 14 | 14 | projects/llm_to_action/source/fmu/fmu_node.hpp |
| 20 | 14 | 14 | projects/llm_to_action/source/fmu/fmu_node_base.hpp |
| 18 | 92 | 1 | build.sh |
| 14 | 84 | 9 | .gitignore |
| 13 | 22 | 2 | projects/llm_to_action/test/lib/sim_core.sh |
| 12 | 19 | 7 | docs/ARCHITECTURE.md |
| 11 | 14 | 14 | projects/llm_to_action/source/fmu/fmu_node.cpp |
| 10 | 28 | 0 | CLAUDE.md |
| 9 | 35 | 7 | tools/devenv/Dockerfile |
| 9 | 33 | 9 | tools/devenv/devenv.sh |
| 8 | 21 | 6 | projects/llm_to_action/source/fmu/CMakeLists.txt |
| 8 | 18 | 14 | projects/llm_to_action/source/CMakeLists.txt |
| 8 | 12 | 14 | projects/llm_to_action/source/fmu/perception_runtime.hpp |
| 8 | 13 | 19 | projects/llm_to_action/source/fmu/llamaclient.hpp |
| 8 | 9 | 19 | projects/llm_to_action/source/fmu/llm_base.hpp |
| 8 | 70 | 23 | build.ps1 |
| 7 | 91 | 2 | README.md |
| 6 | 50 | 2 | dependencies/rubicon.sdf |
| 6 | 7 | 7 | archive/llm_cv_scene/config.py |
| 6 | 6 | 21 | projects/llm_to_action/source/tello_backend/tello_backend.cpp |
| 6 | 6 | 21 | projects/llm_to_action/source/tello_backend/tello_backend.hpp |
| 6 | 6 | 21 | projects/llm_to_action/source/tello_backend/test/tello_teleop.cpp |
| 6 | 2 | 23 | docs/code-guidelines.md |
| 5 | 18 | 2 | projects/llm_to_action/test/sitl-legacy/rubicon/run.sh |
| 5 | 6 | 7 | archive/llm_cv_scene/run_demo.sh |
| 5 | 7 | 7 | archive/llm_cv_scene/vlm.py |
| 5 | 5 | 9 | archive/llm_cv_scene/README.md |
| 5 | 5 | 9 | archive/llm_cv_scene/app.py |
| 5 | 22 | 10 | projects/llm_to_action/source/gstreamer_udp_cam_rx/rx_node.cpp |
| 5 | 13 | 14 | projects/llm_to_action/source/tello_backend/CMakeLists.txt |
| 5 | 24 | 20 | projects/slam/source/slam2.hpp |
| 5 | 6 | 21 | projects/llm_to_action/source/px4_backend/px4_backend.cpp |
| 5 | 3 | 24 | projects/llm_to_action/source/px4_backend/px4_backend.hpp |
| 5 | 1 | 25 | docs/README.md |
| 5 | 53 | 40 | .vscode/launch.json |
| 4 | 20 | 2 | dependencies/rubicon_colors.sdf |
| 4 | 21 | 2 | dependencies/rubicon_targets.sdf |

## Directory aggregate (live files)

| files | total touches | avg | dir |
|--:|--:|--:|---|
| 81 | 250 | 3.1 | projects/llm_to_action/source |
| 88 | 158 | 1.8 | scripts/test |
| 11 | 96 | 8.7 | (root) |
| 71 | 71 | 1.0 | assets/gz_models |
| 14 | 45 | 3.2 | archive/llm_cv_scene |
| 30 | 43 | 1.4 | docs/active |
| 1 | 36 | 36.0 | docs/NOTES.md |
| 27 | 27 | 1.0 | projects/integration_notify |
| 1 | 25 | 25.0 | docs/ROADMAP.md |
| 20 | 21 | 1.1 | projects/integration |
| 20 | 20 | 1.0 | projects/integration_tts |
| 13 | 18 | 1.4 | archive/llm_cv_track |
| 11 | 15 | 1.4 | projects/slam/source |
| 1 | 12 | 12.0 | docs/ARCHITECTURE.md |
| 10 | 10 | 1.0 | assets/gz_world |
| 1 | 9 | 9.0 | tools/devenv/Dockerfile |
| 1 | 9 | 9.0 | tools/devenv/devenv.sh |
| 1 | 6 | 6.0 | dependencies/rubicon.sdf |
| 1 | 6 | 6.0 | docs/code-guidelines.md |
| 6 | 6 | 1.0 | docs/stale |
| 1 | 5 | 5.0 | docs/README.md |
| 1 | 5 | 5.0 | .vscode/launch.json |
| 1 | 4 | 4.0 | dependencies/rubicon_colors.sdf |
| 1 | 4 | 4.0 | dependencies/rubicon_targets.sdf |
| 1 | 4 | 4.0 | .claude/settings.local.json |
| 1 | 4 | 4.0 | cmake/FetchStellaSLAM.cmake |
| 1 | 4 | 4.0 | tools/devenv/devenv.ps1 |
| 1 | 4 | 4.0 | cmake/FetchLLamaCPP.cmake |
| 1 | 4 | 4.0 | .vscode/settings.json |
| 1 | 4 | 4.0 | cmake/BuildDiagnostics.cmake |
| 1 | 4 | 4.0 | cmake/OutputDir.cmake |
| 1 | 4 | 4.0 | cmake/WorkspaceOptions.cmake |
| 1 | 3 | 3.0 | dependencies/default_car.sdf |
| 1 | 3 | 3.0 | dependencies/empty.sdf |
| 1 | 3 | 3.0 | dependencies/harmonic.sdf |
| 1 | 3 | 3.0 | dependencies/moving_person.sdf |
| 1 | 3 | 3.0 | dependencies/rubicon_tree.sdf |
| 1 | 3 | 3.0 | dependencies/three_people.sdf |
| 1 | 3 | 3.0 | .claude/settings.json |
| 1 | 3 | 3.0 | cmake/ColouredOutput.cmake |
| 1 | 3 | 3.0 | cmake/SubmoduleUpdate.cmake |
| 1 | 3 | 3.0 | cmake/UseCCache.cmake |
| 2 | 3 | 1.5 | docs/scheduled |
| 1 | 2 | 2.0 | tools/devenv/build-devenv.sh |
| 2 | 2 | 1.0 | scripts/sandbox |
| 1 | 1 | 1.0 | assets/gz_models |
| 1 | 1 | 1.0 | dependencies/orbit_car.sdf |
| 1 | 1 | 1.0 | tools/prewarm_llama.sh |
| 1 | 1 | 1.0 | scripts/run_fmu_mock.sh |
| 1 | 1 | 1.0 | assets/a2_observability.rviz |
| 1 | 1 | 1.0 | assets/foxglove_layout.json |
| 1 | 1 | 1.0 | assets/orb_vocab.fbow |
| 1 | 1 | 1.0 | assets/px4_sitl.yaml |
| 1 | 1 | 1.0 | assets/stella_config_px4.yaml |
| 1 | 1 | 1.0 | assets/stella_config_tello.yaml |
| 1 | 1 | 1.0 | assets/tello.yaml |
| 1 | 1 | 1.0 | docs/system-architecture.md |
| 1 | 1 | 1.0 | docs/writing-style.md |
| 1 | 1 | 1.0 | cmake/DetectWSL.cmake |
| 1 | 1 | 1.0 | scripts/build.ps1 |
| 1 | 1 | 1.0 | scripts/build.sh |
| 1 | 1 | 1.0 | cmake/FetchOpenVINS.cmake |
| 1 | 1 | 1.0 | cmake/FindGStreamer.cmake |
| 1 | 1 | 1.0 | cmake/FetchCPM.cmake |

## One-shot files — touched in exactly 1 commit, idle >= 5 days (slop candidates)

| idle(d) | born | file |
|--:|--|---|
| 66 | 2026-06-27 | cmake/FetchCPM.cmake |
| 52 | 2026-07-11 | cmake/FindGStreamer.cmake |
| 45 | 2026-07-18 | cmake/FetchOpenVINS.cmake |
| 44 | 2026-07-19 | projects/slam/source/CMakeLists.txt |
| 44 | 2026-07-19 | projects/slam/source/slam1.hpp |
| 44 | 2026-07-19 | projects/slam/source/slam_node.cpp |
| 42 | 2026-07-21 | scripts/build.ps1 |
| 42 | 2026-07-21 | scripts/build.sh |
| 40 | 2026-07-23 | .gitattributes |
| 40 | 2026-07-23 | cmake/DetectWSL.cmake |
| 32 | 2026-07-31 | projects/llm_to_action/source/asr/asr_node_base.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/fmu/spsc_bounded_queue.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/fmu/threadpool.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/gstreamer_gz_udp_tx/gazebo_cam_plugin.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/gstreamer_gz_udp_tx/spsc_ringbuffer.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/keyboard/async_key.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/keyboard/key_codes.cpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/keyboard/key_codes.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/keyboard/keyboard_node.cpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/keyboard/keyboard_node_base.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/offboard_ctrl/px4_offboard_node.cpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/offboard_ctrl/px4_offboard_node.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/offboard_ctrl/px4_offboard_node_base.hpp |
| 32 | 2026-07-31 | projects/llm_to_action/source/util/base.hpp |
| 27 | 2026-08-05 | projects/llm_to_action/source/asr/CMakeLists.txt |
| 27 | 2026-08-05 | projects/llm_to_action/source/keyboard/CMakeLists.txt |
| 24 | 2026-08-08 | docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md |
| 24 | 2026-08-08 | docs/writing-style.md |
| 23 | 2026-08-09 | scripts/sandbox/.gitignore |
| 23 | 2026-08-09 | scripts/sandbox/run.sh |
| 23 | 2026-08-09 | projects/llm_to_action/test/lib/stop_session.sh |
| 23 | 2026-08-09 | projects/llm_to_action/test/lib/wait_for_ground_truth.sh |
| 23 | 2026-08-09 | scripts/test/slam/compare_ground_truth.py |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/approach-real/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/approach/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/battery-landnow/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/battery-rth/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/cross/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/vlm/filter.sh |
| 21 | 2026-08-11 | projects/llm_to_action/test/lib/vlm_log_tool.sh |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/TESTING.md |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/crowd/watch.sh |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/digest.sh |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/follow/watch.sh |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/logtest.sh |
| 20 | 2026-08-12 | projects/llm_to_action/source/fmu/test/target_tracker_test.cpp |
| 20 | 2026-08-12 | projects/llm_to_action/source/perception/target_tracker.hpp |
| 20 | 2026-08-12 | docs/system-architecture.md |
| 20 | 2026-08-12 | projects/llm_to_action/source/tello_backend/test/tello_slam_hold.cpp |
| 20 | 2026-08-12 | projects/slam/source/hover_hold_control.hpp |
| 20 | 2026-08-12 | projects/slam/source/slam_pose_bridge.hpp |
| 20 | 2026-08-12 | projects/slam/source/slam_recovery_fsm.hpp |
| 20 | 2026-08-12 | projects/slam/source/test/hover_hold_control_test.cpp |
| 20 | 2026-08-12 | projects/slam/source/test/hover_hold_sim_test.cpp |
| 20 | 2026-08-12 | projects/slam/source/test/slam_pose_bridge_test.cpp |
| 20 | 2026-08-12 | projects/slam/source/test/slam_recovery_fsm_test.cpp |
| 20 | 2026-08-12 | scripts/test/yolo-quality/README.md |
| 20 | 2026-08-12 | scripts/test/yolo-quality/yolo_quality.py |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/dashboard/.gitignore |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/dashboard/README.md |
| 20 | 2026-08-12 | projects/llm_to_action/test/sitl-legacy/dashboard/run.sh |
| 15 | 2026-08-17 | docs/active/fmu-node-split-map.md |
| 15 | 2026-08-17 | tools/dji_mock/ws_latency.py |
| 14 | 2026-08-18 | assets/a2_observability.rviz |
| 14 | 2026-08-18 | assets/foxglove_layout.json |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/materials/textures/hatchback.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/meshes/hatchback.mtl |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/meshes/hatchback.obj |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/metadata.pbtxt |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/model.config |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/model.sdf |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/thumbnails/1.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/thumbnails/2.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/thumbnails/3.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/thumbnails/4.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback-red/thumbnails/5.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/materials/textures/hatchback.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/materials/textures/wheels3.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/meshes/hatchback.mtl |
| 14 | 2026-08-18 | assets/gz_models/hatchback/meshes/hatchback.obj |
| 14 | 2026-08-18 | assets/gz_models/hatchback/model.config |
| 14 | 2026-08-18 | assets/gz_models/hatchback/model.sdf |
| 14 | 2026-08-18 | assets/gz_models/hatchback/thumbnails/1.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/thumbnails/2.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/thumbnails/3.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/thumbnails/4.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback/thumbnails/5.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/materials/textures/hatchback.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/meshes/hatchback.mtl |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/meshes/hatchback.obj |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/metadata.pbtxt |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/model.config |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/model.sdf |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/thumbnails/1.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/thumbnails/2.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/thumbnails/3.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/thumbnails/4.png |
| 14 | 2026-08-18 | assets/gz_models/hatchback_blue/thumbnails/5.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/eyebrow001-unmodified.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/eyebrow001.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/green_eye.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/jeans01_normals.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/jeans_basic_diffuse.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/male02_diffuse_black-unmodified.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/male02_diffuse_black.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/teeth.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/tshirt02_normals.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/tshirt02_texture.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/materials/textures/young_lightskinned_male_diffuse.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/meshes/standing.dae |
| 14 | 2026-08-18 | assets/gz_models/person_standing/model.config |
| 14 | 2026-08-18 | assets/gz_models/person_standing/model.sdf |
| 14 | 2026-08-18 | assets/gz_models/person_standing/thumbnails/1.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/thumbnails/2.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/thumbnails/3.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/thumbnails/4.png |
| 14 | 2026-08-18 | assets/gz_models/person_standing/thumbnails/5.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/eyebrow001-unmodified.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/eyebrow001.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/green_eye.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/jeans01_normals.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/jeans_basic_diffuse.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/male02_diffuse_black-unmodified.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/male02_diffuse_black.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/teeth.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/tshirt02_normals.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/tshirt02_texture.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/materials/textures/young_lightskinned_male_diffuse.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/meshes/walking.dae |
| 14 | 2026-08-18 | assets/gz_models/person_walking/model.config |
| 14 | 2026-08-18 | assets/gz_models/person_walking/model.sdf |
| 14 | 2026-08-18 | assets/gz_models/person_walking/thumbnails/1.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/thumbnails/2.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/thumbnails/3.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/thumbnails/4.png |
| 14 | 2026-08-18 | assets/gz_models/person_walking/thumbnails/5.png |
| 14 | 2026-08-18 | assets/gz_world/default_car.sdf |
| 14 | 2026-08-18 | assets/gz_world/empty.sdf |
| 14 | 2026-08-18 | assets/gz_world/harmonic.sdf |
| 14 | 2026-08-18 | assets/gz_world/moving_person.sdf |
| 14 | 2026-08-18 | assets/gz_world/orbit_car.sdf |
| 14 | 2026-08-18 | assets/gz_world/rubicon.sdf |
| 14 | 2026-08-18 | assets/gz_world/rubicon_colors.sdf |
| 14 | 2026-08-18 | assets/gz_world/rubicon_targets.sdf |
| 14 | 2026-08-18 | assets/gz_world/rubicon_tree.sdf |
| 14 | 2026-08-18 | assets/gz_world/three_people.sdf |
| 14 | 2026-08-18 | assets/orb_vocab.fbow |
| 14 | 2026-08-18 | assets/px4_sitl.yaml |
| 14 | 2026-08-18 | assets/stella_config_px4.yaml |
| 14 | 2026-08-18 | assets/stella_config_tello.yaml |
| 14 | 2026-08-18 | assets/tello.yaml |
| 14 | 2026-08-18 | docs/specs/spec-dji-endtoend-bringup.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/hover/README.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/hover/filter.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/hover/run.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/obstacle-stop/README.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/obstacle-stop/filter.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/obstacle-stop/run.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow-airborne/README.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow-airborne/filter.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow-airborne/run.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow/README.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow/filter.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/queue-overflow/run.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/rotate/README.md |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/rotate/filter.sh |
| 14 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/rotate/run.sh |
| 14 | 2026-08-18 | archive/llm_cv_scene/ears.py |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_status_parse.hpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_ws.hpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_ws_raw.cpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_ws_wspp.cpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/test/dji_backend_mock_test.cpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/test/dji_ws_test.cpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/fmu/fmu_helpers.hpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/fmu/test/fmu_test_scenarios.hpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/CMakeLists.txt |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_backend.cpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/dji_backend.hpp |
| 14 | 2026-08-18 | projects/llm_to_action/source/dji_backend/test/dji_latency_probe.cpp |
| 12 | 2026-08-20 | archive/llm_cv_scene/_app_rtmp_launch.sh |
| 12 | 2026-08-20 | archive/llm_cv_scene/recognize.py |
| 12 | 2026-08-20 | archive/llm_cv_track/run_track.sh |
| 12 | 2026-08-20 | archive/llm_cv_track/track.py |
| 11 | 2026-08-21 | archive/llm_cv_track/botsort_reid.yaml |
| 11 | 2026-08-21 | archive/llm_cv_track/follow.py |
| 11 | 2026-08-21 | archive/llm_cv_track/recognize_omdet.py |
| 11 | 2026-08-21 | archive/llm_cv_track/run_follow.sh |
| 11 | 2026-08-21 | archive/llm_cv_track/run_highlight_seg.sh |
| 10 | 2026-08-22 | docs/active/dji-phone-build-graphene-runbook.md |
| 10 | 2026-08-22 | docs/active/latency-2026-08-22/README.md |
| 10 | 2026-08-22 | docs/active/latency-2026-08-22/latency_overlay.png |
| 10 | 2026-08-22 | docs/active/latency-2026-08-22/latency_overview.png |
| 10 | 2026-08-22 | tools/dji_mock/README.md |
| 10 | 2026-08-22 | tools/dji_mock/dji_check.sh |
| 10 | 2026-08-22 | tools/dji_mock/measure_telemetry.py |
| 10 | 2026-08-22 | tools/dji_mock/measure_video_e2e.py |
| 10 | 2026-08-22 | tools/dji_mock/measure_ws_rtt.py |
| 10 | 2026-08-22 | tools/dji_mock/probe_video.py |
| 9 | 2026-08-23 | docs/active/exoskeletons-android-studio-handoff.md |
| 9 | 2026-08-23 | archive/llm_cv_scene/voice.py |
| 7 | 2026-08-25 | scripts/test/router/live_mock_smoke.py |
| 7 | 2026-08-25 | scripts/test/router/test_router.py |
| 7 | 2026-08-25 | archive/llm_cv_track/run_mvd.sh |
| 7 | 2026-08-25 | projects/llm_to_action/source/dashboard/README.md |
| 7 | 2026-08-25 | projects/llm_to_action/source/dashboard/assess.py |
| 7 | 2026-08-25 | projects/llm_to_action/source/dashboard/mock_data.py |
| 7 | 2026-08-25 | projects/llm_to_action/source/dashboard/serve.py |
| 7 | 2026-08-25 | docs/active/mvd-voice-command-table.md |
| 7 | 2026-08-25 | projects/integration/README.md |
| 7 | 2026-08-25 | projects/integration/__init__.py |
| 7 | 2026-08-25 | projects/integration/camera_stream.py |
| 7 | 2026-08-25 | projects/integration/commands.py |
| 7 | 2026-08-25 | projects/integration/dji_wire.py |
| 7 | 2026-08-25 | projects/integration/ears.py |
| 7 | 2026-08-25 | projects/integration/eyes.py |
| 7 | 2026-08-25 | projects/integration/highlight_seg.py |
| 7 | 2026-08-25 | projects/integration/phone_ears.py |
| 7 | 2026-08-25 | projects/integration/router.py |
| 7 | 2026-08-25 | projects/integration/run_llama_server.sh |
| 7 | 2026-08-25 | projects/integration/run_mvd.sh |
| 7 | 2026-08-25 | projects/integration/run_router.py |
| 7 | 2026-08-25 | projects/integration/scene_omdet.py |
| 7 | 2026-08-25 | projects/integration/test_router.py |
| 7 | 2026-08-25 | projects/integration/video_doctor.py |
| 7 | 2026-08-25 | projects/integration/video_watchdog.py |
| 7 | 2026-08-25 | projects/integration/vlm.py |
| 7 | 2026-08-25 | projects/integration/voice.py |
| 6 | 2026-08-26 | docs/active/2026-08-26-session-postmortem-brief-defects.md |
| 6 | 2026-08-26 | docs/stale/2026-08-20-djibackend-handoff.md |
| 6 | 2026-08-26 | docs/stale/2026-08-20-phase2-detector-feeltest.md |
| 6 | 2026-08-26 | docs/stale/2026-08-21-drone-bringup-status-and-next.md |
| 6 | 2026-08-26 | docs/stale/demo-roadmap-2026-08-28.md |
| 6 | 2026-08-26 | docs/stale/mission-brief-2026-08-15.md |
| 6 | 2026-08-26 | docs/stale/spec-android-docker-bridge.md |

235 one-shot files.

## Two-touch files — 2 commits, idle >= 5 days (weak-tool candidates)

| idle(d) | born | last | file |
|--:|--|--|---|
| 27 | 2026-08-05 | 2026-08-05 | projects/llm_to_action/source/px4_backend/test/frame_convert_test.cpp |
| 27 | 2026-08-05 | 2026-08-05 | projects/llm_to_action/source/tello_backend/test/tello_convert_test.cpp |
| 27 | 2026-07-31 | 2026-08-05 | projects/llm_to_action/source/fmu/llamaclient.cpp |
| 27 | 2026-07-31 | 2026-08-05 | projects/llm_to_action/source/gstreamer_gz_udp_tx/CMakeLists.txt |
| 26 | 2026-08-05 | 2026-08-06 | projects/llm_to_action/source/frame/frame_convert.hpp |
| 24 | 2026-07-31 | 2026-08-08 | projects/llm_to_action/source/keyboard/keyboard_node.hpp |
| 23 | 2026-08-05 | 2026-08-09 | projects/llm_to_action/source/offboard_ctrl/CMakeLists.txt |
| 23 | 2026-08-08 | 2026-08-09 | docs/scheduled/2026-08-08-runtime-drone-config-constants.md |
| 22 | 2026-08-05 | 2026-08-10 | projects/llm_to_action/source/fmu/plan_parse.hpp |
| 21 | 2026-08-11 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/override/README.md |
| 21 | 2026-08-11 | 2026-08-11 | projects/llm_to_action/test/sitl-legacy/override/filter.sh |
| 20 | 2026-08-12 | 2026-08-12 | docs/active/asr-noise-robustness.md |
| 20 | 2026-07-31 | 2026-08-12 | projects/llm_to_action/source/gstreamer_gz_udp_tx/gazebo_cam_plugin_base.hpp |
| 20 | 2026-08-11 | 2026-08-12 | projects/llm_to_action/source/fmu/drone_config.hpp |
| 14 | 2026-08-12 | 2026-08-18 | NOTE.md |
| 14 | 2026-08-17 | 2026-08-18 | docs/active/dji-apiserver-review.md |
| 14 | 2026-08-08 | 2026-08-18 | scripts/test/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach-impact/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach-impact/filter.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach-impact/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach-real/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach-real/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/approach/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/battery-landnow/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/battery-landnow/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/battery-rth/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/battery-rth/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/cross/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/cross/run.sh |
| 14 | 2026-08-12 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/crowd/run.sh |
| 14 | 2026-08-12 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/follow/README.md |
| 14 | 2026-08-12 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/follow/filter.sh |
| 14 | 2026-08-12 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/follow/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/interrupt-storm/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/interrupt-storm/filter.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/interrupt-storm/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/override/run.sh |
| 14 | 2026-08-13 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/rubicon_orbit/run.sh |
| 14 | 2026-08-12 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/search_follow/run.sh |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/vlm/README.md |
| 14 | 2026-08-11 | 2026-08-18 | projects/llm_to_action/test/sitl-legacy/vlm/run.sh |
| 14 | 2026-08-09 | 2026-08-18 | scripts/test/slam/README.md |
| 14 | 2026-08-05 | 2026-08-18 | projects/llm_to_action/source/generic_backend/active_backend.hpp |
| 14 | 2026-08-05 | 2026-08-18 | projects/llm_to_action/source/px4_backend/CMakeLists.txt |
| 13 | 2026-08-18 | 2026-08-19 | archive/llm_cv_scene/.gitignore |
| 13 | 2026-07-31 | 2026-08-19 | projects/llm_to_action/source/asr/asr_node.hpp |
| 12 | 2026-08-20 | 2026-08-20 | archive/llm_cv_track/.gitignore |
| 11 | 2026-08-20 | 2026-08-21 | archive/llm_cv_track/README.md |
| 10 | 2026-08-18 | 2026-08-22 | docs/runbooks/dji-bringup-runbook.md |
| 10 | 2026-08-18 | 2026-08-22 | docs/active/dji-video-h264-over-tcp.md |
| 10 | 2026-08-18 | 2026-08-22 | tools/dji_mock/video_tcp_mock.py |
| 10 | 2026-08-18 | 2026-08-22 | projects/llm_to_action/source/dji_backend/dji_backend_base.hpp |
| 10 | 2026-08-18 | 2026-08-22 | projects/llm_to_action/source/dji_backend/test/dji_convert_test.cpp |
| 9 | 2026-08-22 | 2026-08-23 | tools/dji_mock/plot_latency.py |
| 7 | 2026-08-19 | 2026-08-25 | tools/devenv/build-devenv.sh |
| 7 | 2026-08-20 | 2026-08-25 | archive/llm_cv_scene/run_demo_rtmp.sh |
| 7 | 2026-08-21 | 2026-08-25 | archive/llm_cv_track/highlight_seg.py |
| 7 | 2026-08-21 | 2026-08-25 | archive/llm_cv_track/run_scene_omdet.sh |
| 7 | 2026-08-21 | 2026-08-25 | archive/llm_cv_track/scene_omdet.py |
| 6 | 2026-08-22 | 2026-08-26 | docs/active/final-objective-context.md |
| 6 | 2026-08-18 | 2026-08-26 | docs/active/fmu-cleanup-tasklist.md |
| 6 | 2026-08-22 | 2026-08-26 | docs/runbooks/kill-switch-verification.md |
| 6 | 2026-08-17 | 2026-08-26 | docs/specs/spec-dji-websocket-protocol.md |
| 6 | 2026-08-25 | 2026-08-26 | projects/integration/config.py |

65 two-touch files.
