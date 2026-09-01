# RoboMaster S1 — concrete jailbreak + interface runbook (2026-08-26)

Execute top to bottom. Companion to `2026-08-26-s1-interface-jailbreak-guide.md` (odds + firmware
ladder). This file is the exact commands. Every payload referenced is already on disk under
`source/robomaster/hack-collabnix/`. Legitimacy: enabling DJI's own EP SDK on an S1 we own.

Absolute paths assume the repo at `/root/groundstation`. Adjust if different.

---

## Mechanism (know what each step does before you run it)

1. `root.py_s1`, pasted into the app's Lab -> Python and Run, escapes the Python sandbox and runs
   `/system/bin/adb_en.sh` on the robot. That turns on **adbd**, so the laptop can `adb shell` in.
2. `upload.sh` (run on the laptop, FROM the extracted zip dir) pushes over adb: the EP SDK tree
   into `/data/dji_scratch/`, a **modified `dji_scratch.py`** into `/data/dji_scratch/bin/`, and
   EP's `dji.json` + `dji_hdvt_uav` + `patch.sh` into `/data/`.
3. On the next **boot**, the modified `/data/dji_scratch/bin/dji_scratch.py` (line 21) runs
   `subprocess.Popen(["/system/bin/sh","/data/patch.sh"])`. `patch.sh` bind-mounts EP's `dji.json`
   over `/system/etc/dji.json` and EP's `dji_hdvt_uav` over `/system/bin/dji_hdvt_uav`, then
   restarts `dji_sys` / `dji_hdvt_uav` / `dji_vision`. That is what enables the SDK. **You never run
   `patch.sh` by hand** — the boot script does, every boot, which is why the unlock persists.
4. Two chimes on boot = patch applied. SDK then listens on TCP **40923** (text), **40921** (video),
   **20020** (binary).

---

## Prerequisites (do these BEFORE the robot session)

```bash
# 1. adb on the laptop (NOT present on this workstation today):
adb version || sudo apt-get install -y android-tools-adb

# 2. Extract the unlock zip — REQUIRED. upload.sh pushes dji_scratch/sdk and
#    dji_scratch/bin/dji_scratch.py, which exist ONLY inside the zip, not in the loose folder.
cd /root/groundstation/source/robomaster/hack-collabnix
rm -rf s1_sdk_hack && unzip s1_sdk_hack.zip     # -> ./s1_sdk_hack/
ls s1_sdk_hack/dji_scratch/bin/dji_scratch.py   # must exist, else upload.sh fails
```

---

## STEP 1 — probe: is it ALREADY unlocked? (read-only, zero risk)

Put the robot in direct/AP mode in the app. Join its Wi-Fi (SSID `RMS1-XXXXXX`). Robot = `192.168.2.1`.

```bash
python3 /root/groundstation/source/robomaster/s1_probe.py
```
- `*** SDK MODE ENABLED ***`  -> already unlocked (or it is an EP). **Skip to STEP 5.**
- `CONNECT FAILED` / no `ok;`  -> LOCKED. First confirm the firmware is unlock-safe
  (`<= 00.06.0300`; see the guide's ladder). Then continue.

---

## STEP 2 — enable adb on the robot (the root payload)

1. Connect the robot to the laptop with the **USB-C cable**.
2. In the RoboMaster app: **Lab -> Python -> new program**. Open
   `/root/groundstation/source/robomaster/hack-collabnix/root.py_s1`, copy its ENTIRE contents,
   paste into the Lab editor.
3. Press **Run**. It returns almost immediately with no visible output. That is expected — it
   forked `adb_en.sh` in the background.
   - If Lab throws an exception here (e.g. `__import__` / sandbox error), your **firmware is
     patched**. The software root is dead on this unit. Stop; see the guide's section 6 (fallbacks).
4. On the laptop, confirm the robot now exposes adb:
```bash
adb kill-server; adb start-server
adb devices        # expect one device listed (serial + "device")
```
   - Empty list, and you are on this containerized workstation? Re-create the USB node, then retry:
```bash
bash /root/groundstation/exoskeletons/tools/adbfix.sh   # container USB re-enumeration fix
adb devices
```
   - Still empty on bare metal: replug USB-C, re-run `root.py_s1` (adbd may not have started).

---

## STEP 3 — push the SDK payload (from the extracted dir)

```bash
cd /root/groundstation/source/robomaster/hack-collabnix/s1_sdk_hack   # MUST be this dir
adb shell 'ls /data/dji_scratch' 2>/dev/null    # sanity: adb shell works
bash upload.sh
```
`upload.sh` runs five `adb push`es. Watch for `error: device not found` (adb dropped — redo STEP 2)
or `No such file or directory` (you are in the wrong dir — you must be inside `s1_sdk_hack/`).
Each push should print a bytes-transferred line. No push should error.

Verify the payload landed:
```bash
adb shell 'ls -l /data/dji.json /data/dji_hdvt_uav /data/patch.sh /data/dji_scratch/bin/dji_scratch.py'
```
All four must exist.

---

## STEP 4 — reboot and confirm

1. Power the robot OFF, then ON (hardware switch — a clean reboot triggers the boot hook).
2. **Listen on boot: TWO chimes = success.** One chime = the patch did not apply (re-check STEP 3
   pushed `dji_scratch.py` and `patch.sh`; re-run STEP 2->3).
3. Rejoin the robot Wi-Fi, re-probe:
```bash
python3 /root/groundstation/source/robomaster/s1_probe.py
# expect: *** SDK MODE ENABLED ***
```

---

## STEP 5 — interface: prove video, then text (the demo-critical order)

```bash
cd /root/groundstation/source/robomaster

# 5a. Camera H.264 actually flows (THE make-or-break for our use):
python3 s1_video.py 192.168.2.1 8 /tmp/s1.h264
#   VERDICT: *** VIDEO FLOWS ***   then play it:
ffplay -f h264 /tmp/s1.h264

# 5b. Text API sanity (SDK mode + version + telemetry, NO motion):
python3 s1_text.py
#   add --move only with the robot secured / off a table (one small gimbal nudge)
#   add --chassis only with WHEELS OFF THE GROUND (it will try to drive)
```

---

## STEP 6 — wire the S1 camera into the perception stack (~1 h)

Same H.264-over-TCP shape as the drone feed. Two routes; both keep chassis motion off.

**Fast route (no shared-C++ change).** Feed GStreamer straight into scene_omdet:
```bash
cd /root/groundstation/source/integration
# start the stream first (s1_video.py sends `stream on;`), then:
SCENE_INPUT="tcpclientsrc host=192.168.2.1 port=40921 ! h264parse ! avdec_h264 ! videoconvert ! appsink" \
  python3 scene_omdet.py
```
(Match the exact GStreamer tail scene_omdet expects — copy the drone `SCENE_INPUT` pipeline and swap
the source element for `tcpclientsrc host=192.168.2.1 port=40921`.)

**Clean route (the ONE allowed shared-C++ touch).** Point the receiver at 40921 so it publishes
`camera/stream`, then run scene_omdet with `SCENE_INPUT=ros` — byte-identical to the drone path:
```bash
build/release/shared/dji/bin/llm_to_action_gstreamer_rx --host 192.168.2.1 --port 40921
# (verify the flag names against gstreamer_udp_cam_rx/rx_node; --dji hardcodes 5600)
```

---

## Quick failure map

| Symptom | Cause | Action |
|---|---|---|
| Lab Run throws exception | firmware patched | software root dead; guide section 6 |
| `adb devices` empty (container) | USB node stale | `adbfix.sh`, retry |
| upload.sh `No such file` | wrong dir | `cd .../s1_sdk_hack` first |
| one chime after reboot | patch didn't apply | re-verify STEP 3 pushes, redo 2->3 |
| probe ENABLED but video empty | stream not started / codec | ensure `stream on;` ok reply; try `ffplay -f h264` |
