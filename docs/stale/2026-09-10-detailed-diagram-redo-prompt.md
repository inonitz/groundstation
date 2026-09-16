Produce a DETAILED architecture diagram of the integration_harden2 system for demo-day slides. Derive it YOURSELF from the SOURCE CODE, from scratch. This also tests the `diagram-authoring` skill.

STEP 1: Invoke the diagram-authoring skill (Skill tool, skill="diagram-authoring"). Read and follow it.

STEP 2: Deep-dive the SOURCE CODE and reach your OWN conclusion. Read the actual CODE, not any existing diagram. Do NOT read any .dot/.svg/.drawio under docs/active/assets — those are other people's conclusions. Read at least:
- projects/integration_harden/scene_omdet.py (the ground-station orchestrator — start here)
- projects/integration_harden/recognizer/ (pipeline.py, recognizer.py, llama.py, prompts.py)
- projects/integration_harden/perception2/ and perception/ (concept.py, engine.py, sam3_backend.py, detectors.py)
- projects/integration_harden/control/ (router.py, dji_wire.py, kill.py)
- projects/integration_harden/audio/ and video/ (ros2_asr.py, phone_asr.py, tts_io.py, camera_stream.py)
- projects/integration_harden/run_mvd.sh
- The phone Kotlin API server: `rtk grep -rn "ApiServer|/c/ws/sticks|VideoTcpServer" projects` then read it.
Trace real components, ports, flows, and directions. The drone's only link is the DJI Remote (AirLink). Video path: drone -> RC -> phone -> gstreamer -> ROS2.

DESIGN RULES — the first detailed attempt was REJECTED for these faults. Do not repeat them:
1. It grouped and titled boxes BY SOURCE FILE. Wrong. Title each box by its ROLE. A source filename may appear as ONE small dim annotation line inside a box, never as the title and never as the grouping principle.
2. It dumped every attribute into every block. Do NOT. Each box: a role title plus AT MOST 3 short lines of the essential detail (key port, model, protocol).
3. "Detailed" means MORE information than a simplified slide, but it must still READ WELL. Balance and whitespace matter as much as content.

STRUCTURE:
- Group the system into SUBSYSTEM clusters, for example: Operator; Ground station (the brain); Phone app (recon-swarm); RF link + aircraft.
- Inside each cluster, 2 to 5 role boxes. Total boxes: aim for 12 to 18. Fewer, richer boxes beat many thin ones.
- KEEP every real detail that a reviewer needs: ApiServer :8080 routes, video :5600, planner/VLM llama-server :18090 (Gemma 4, Vulkan), translator :18091, ASR (Whisper Hebrew), SAM3 perception, Router tiers, virtual sticks, mock vs real (MVD_WIRE_REAL, human-run), ROS2 topics, KillSwitch.
- Keep true flow directions. Wider slide aspect is fine for detailed (about 1.4:1).

STEP 3: author harden2-detailed.dot (splines=ortho), render with the skill's gvcairo.py, measure margins with `dot -Tplain`, fix any margin under 0.4 in by repositioning, then run clean_svg.py. Verify: 0 `<text>` elements, hex colors only, no overflow.

OUTPUT ONLY to:
  /root/groundstation/docs/active/assets/diagrams-final/harden2-detailed.svg
  /root/groundstation/docs/active/assets/diagrams-final/harden2-detailed.png
  /root/groundstation/docs/active/assets/diagrams-final/harden2-detailed.dot

Use rtk read/grep for all reads. Run NO git commands.
FINAL ACTION when fully done and verified: write the single word DONE to
  /root/groundstation/docs/active/assets/diagrams-final/harden2-detailed.DONE
