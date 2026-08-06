# Tello Real-World Bring-Up & Telemetry Hardening

**Date:** 2026-08-06
**Status:** Closed — first real-hardware validation of the Tello backend. Telemetry/odometry fixed and flight-verified; one config change left staged for manual commit.

## What This Session Really Was
This was the drone's first honest contact with reality. The backend had been written but never proven against live hardware, and the moment it met a real Tello the state telemetry was 100% dead. The work was equal parts **validation** (does the code actually fly a real drone?) and **hardening** (making the launch path survive the real-world environment — firewalls, ephemeral containers, a flaky AP link). "Hardening" is a mild stretch, but a fair one: without testing against reality and fixing what broke, the drone would not have flown at all.

## Objective (as stated at session start)
Verify the drone's SDK version, get state telemetry working, get odometry and camera streams working, and decide whether the drone needs an EDU/SDK-2.0 firmware flash.

## Outcome Summary
State telemetry and odometry were fully root-caused, fixed, and verified on real hardware. The camera stream turned out to already work (an early misread on my part). The SDK-version and firmware questions were answered definitively. One config change (`scripts/devenv.sh`) is left staged for the user to commit with their own message.

## Root Cause (state telemetry was 100% dead)
The host's firewall ran a default-deny `INPUT` policy (`policy DROP`). Tello's **state broadcasts arrive as unsolicited inbound UDP on port 8890** and were dropped at the netfilter layer before reaching the app's socket. The **command channel (UDP 8889) worked** only because our own outbound `command`/`rc` sends create a `ctstate ESTABLISHED` conntrack entry that lets replies back in — state traffic has no such matching flow.

The debugging was drawn out because the first fix *looked* applied but wasn't:
- `sudo ufw allow 8890/udp` (and 11111) printed "Rules updated" and `ufw status verbose` listed both rules as active — yet telemetry stayed dead.
- `tcpdump` proved **585 genuine Tello state packets** were on the wire during a live run (src `192.168.10.1:8889` → dst `192.168.10.2:8890`, ASCII payload `pitch:…;roll:…;bat:…;agz:…`) while the app saw zero.
- `iptables -L ufw-user-input` showed that chain held only an unrelated `tcp/24800` rule — **ufw's 8890/11111 ACCEPTs never landed in the kernel**.
- `iptables -L INPUT` showed the `ufw-user-input` jump chain was **missing from INPUT entirely**.
- Cause: ufw had been uninstalled + reinstalled mid-session inside the container during earlier debugging. The reinstall desynced ufw's on-disk rule files from live netfilter and dropped the INPUT→ufw-user-input jump. Even after manually re-inserting the jump, an `nc` synthetic test on 8890 still failed — the chain itself contained no matching rule. **ufw's apply mechanism is fundamentally broken in this container image.**

## The Fix
Bypass ufw completely and insert raw netfilter rules:
```bash
iptables -I INPUT 1 -p udp --dport 8890 -j ACCEPT
iptables -I INPUT 1 -p udp --dport 11111 -j ACCEPT
```
**Verified on hardware:** `nc -u -l -p 8890` received live state immediately after `command` was sent; then a full `./tello_teleop` flight showed `[state] first valid GetState() parsed OK` right away and `stateMisses=0` across the entire takeoff → hover → move → land cycle. Odometry (`[tele]` alt/vel/yaw) is live every cycle as a direct result.

## Key Networking Facts (confirmed, worth recording in ARCHITECTURE.md)
- The dev container launches with `--net=host --privileged`, so it **shares the host's netfilter tables 1:1**. `iptables` run inside the container operates on the real host kernel tables. The fix therefore belongs *inside* the container startup (runs as root, no `sudo`), which is where `devenv.sh` now places it.
- A false trail was corrected during the session: the iptables lines were briefly written to run on the host *before* `docker run` — wrong, because every working command this session ran inside the container and the host may not even have `iptables`. They now run inside the container's `bash -c` startup.

## Camera / Video: Works (corrected)
Early in the session I claimed video was broken based on `non-existing PPS 0 referenced` / `no frame!` h264 errors. That was a misread — those errors cluster only at **stream start**, before the first SPS/PPS keyframe lands, then stop. The user confirmed the live feed renders in the OpenCV window. `cv::VideoCapture("udp://0.0.0.0:11111", CAP_FFMPEG)` works on hardware. **No gstreamer-pipeline swap is needed** (the fallback documented in `docs/tello_backend_notes.md` can stay on the shelf).

## SDK Version & Firmware Flash: Answered
The drone replies `unknown command` to both `sn?` and `sdk?` — these are SDK-2.0-only queries. This is a **standard/consumer Tello on SDK 1.3, not a Tello EDU.**

SDK 2.0 is **hardware-locked to the Tello EDU model** — you cannot flash a standard Tello up to 2.0. The only 2.0 feature relevant to this project is **video-stream control (`setfps` / `setresolution` / `setbitrate`)**; without it the stream is fixed at roughly 720p30. Mission pads and station mode are the other 2.0/EDU features and neither is needed now. **Verdict: don't pursue a flash. If stream tuning ever becomes critical for the perception pipeline, that's a hardware-purchase decision (buy an EDU), not a firmware one.**

## Files Changed
- **`scripts/Dockerfile`** — `iptables`, `conntrack`, `ufw` added to the apt install list. **Already committed** (in HEAD from a prior commit; not a pending change). Note: only `iptables` is actually required now. `ufw` is proven broken and `conntrack` was debug-only — both are dead weight and could be trimmed for a leaner image.
- **`scripts/devenv.sh`** — the two iptables ACCEPT rules were folded into the container startup, refactored into a readable multi-line `ContainerStartupCmd` variable. **Left modified + unstaged** at session close — the user is writing their own commit message.
- Unrelated pre-existing changes are also in the working tree and were **not** touched this session: `docs/NOTES.md`, `docs/ROADMAP.md`, `scripts/simenv_llm.sh`, `source/llm_to_action/fmu/fmu_node.hpp`, `source/llm_to_action/fmu/fmu_node_base.hpp`, deleted `output.txt`.

## Machine Topology (important context for the master session)
There are two machines: **`swapgs`** (the dev box — where editing, git, and this session run) and **`mint0`** (the laptop physically joined to the Tello's Wi-Fi AP, where the drone code is built and flown). Edits made on swapgs do not appear on mint0 until pushed and pulled. The telemetry fix must ultimately take effect on **mint0**; since it lives in `devenv.sh`, it applies automatically once mint0 pulls the change and relaunches.

## Open Items / Next Steps
1. Commit `scripts/devenv.sh` (user writing the message), push from swapgs, pull on mint0.
2. **Cold-boot verification still owed:** after the next image rebuild + `devenv.sh` launch on mint0, run `iptables -L INPUT -n --line-numbers | head -3` and confirm udp 8890 + 11111 ACCEPT sit at the top. This confirms the rule lands on a *fresh* container, not just the warm one we tested.
3. Optional: trim `conntrack` + `ufw` from the Dockerfile.
4. Firmware: no action — documented as hardware-locked.
5. Resume the actual feature track: **FMU perception integration, block 4.2** (per the prior handoff). This telemetry work was a prerequisite detour, now cleared.
