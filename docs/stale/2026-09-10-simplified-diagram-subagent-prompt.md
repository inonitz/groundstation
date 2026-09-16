Produce a SIMPLIFIED architecture diagram of the integration_harden2 system for a demo SLIDE. The audience is a system reviewer, not a code auditor. This tests the `diagram-authoring` skill.

SOURCE OF TRUTH — DO NOT RE-DIG THE SOURCE:
The full, source-derived architecture is already captured in:
  /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-detailed-TEST.dot
Read THAT file for every component, port, and flow. Do NOT re-read projects/integration_harden/ — the information is already gathered. You may read the diagram-authoring skill.

OWNER FEEDBACK ON THE DETAILED VERSION (obey these):
1. It grouped boxes BY SOURCE FILE. Wrong for a reviewer. DROP all filenames (no router.py, no scene_omdet.py). Name each box by its ROLE.
2. It dumped every detail into every block. DO NOT. One short role line per box. Keep only the ports/protocols that matter to a reviewer.
3. Abstract UP: aim for 7 to 10 boxes total, not 30.
4. Make it LOOK good: balanced layout, real whitespace, clean orthogonal lines, labels centered on their lines.

KEEP THESE TRUE (from the detailed dot):
- The real external boundary and data-flow directions.
- Control up: Operator voice -> Ground station -> phone ApiServer :8080 -> DJI RC (AirLink) -> drone.
- Video down: drone -> RC -> phone VideoTcpServer :5600 -> gstreamer -> ROS2.
- The drone's only radio link is the DJI RC (AirLink).

SUGGESTED GROUPS (adapt from the detailed dot, by ROLE not file):
- Operator (voice in, Hebrew TTS out)
- Ground station brain: 3-4 role boxes only — ASR, Planner/VLM (Gemma 4, Vulkan), Router, Perception (SAM3). No per-file boxes.
- Phone app (recon-swarm): ApiServer :8080 + MSDK virtual sticks + video server :5600, as ONE or TWO boxes.
- DJI RC / AirLink (the only link)
- DJI drone (flight controller + camera + gimbal)

PIPELINE:
STEP 1: invoke the diagram-authoring skill (Skill tool).
STEP 2: author harden2-simplified-TEST.dot (splines=ortho), render with the skill's gvcairo.py, measure margins with `dot -Tplain`, fix any margin under 0.4 in by repositioning, then run clean_svg.py.
STEP 3: verify: 0 `<text>` elements, hex colors only, no overflow, slide aspect near 1.3:1.

OUTPUT ONLY to:
  /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-simplified-TEST.svg
  /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-simplified-TEST.png
  /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-simplified-TEST.dot

Use rtk read/grep for all reads. Run NO git commands.
FINAL ACTION when fully done and verified: write the single word DONE to
  /root/groundstation/docs/active/assets/diagrams-agent-tests/harden2-simplified-TEST.DONE
