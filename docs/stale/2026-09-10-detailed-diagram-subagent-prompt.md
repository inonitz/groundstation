Produce a DETAILED architecture diagram of the integration_harden2 system, derived by YOU from the SOURCE CODE. This tests the `diagram-authoring` skill.

STEP 1: Invoke the diagram-authoring skill (Skill tool, skill="diagram-authoring"). Read and follow it.

STEP 2: Deep-dive the source code and reach your OWN conclusion about the architecture. Read the actual CODE. Do NOT read any existing diagram (no .dot/.svg/.drawio under docs/active/assets) — those are other people's conclusions. Read at least:
- projects/integration_harden/scene_omdet.py (the ground-station orchestrator — start here)
- projects/integration_harden/recognizer/ (pipeline.py, recognizer.py, llama.py, prompts.py)
- projects/integration_harden/perception2/ (concept.py, __init__.py)
- projects/integration_harden/video/camera_stream.py
- projects/integration_harden/run_mvd.sh and any dji_wire / API client
- The phone Kotlin API server: `rtk grep -rn "ApiServer|/c/ws/sticks|VideoTcpServer" projects` then read it.
Trace real components, ports, flows, directions. The drone talks only to the DJI Remote (AirLink); video: drone->RC->phone->gstreamer. Note anything not in the code.

STEP 3: Author your OWN detailed .dot and render via the skill's pipeline: ortho, gvcairo.py, measure margins with `dot -Tplain` and fix any under 0.4 in by repositioning, clean_svg.py, verify 0 <text>/hex/no-overflow/slide-aspect.

Output ONLY to /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-detailed-TEST.svg, .png, .dot.
Use rtk read/grep for all reads. Run NO git commands.
