# SLAM testing guide (Agent 5)

How to test the SLAM / hover-hold work end to end. Everything is one command to start,
and every drone run writes a UNIQUE timestamped log so we can correlate what you flew to
the exact file. Send me the `.digest.txt`.

Order matters: prove the math offline, screen the venue surface, then fly C1 for the
go/no-go. Only after C1 passes do the hover / recovery tests mean anything.

---

## Test 0 — offline unit tests (no drone, no build, ~2 s)

Proves the control math before anything flies: the map->ENU + height-scale bridge, the
degrade-then-land recovery FSM, the hover-hold PID, and a closed-loop drift-mitigation
sim.

```bash
cd /root/groundstation/scripts/tello/slam
./runtests.sh
```

**Good:** `4 passed, 0 failed`, exit 0. The sim line should read roughly
`open-loop=3.00m  closed-loop=0.030m` — that is the drift the controller cancels.

Run this after any change to a SLAM header; it is the regression gate.

---

## Test 1 — venue surface pre-screen (no flying)

Answers one question: will stella / the VPS even track on these surfaces?

**Live (recommended -- walk around handheld):**
```bash
./feature_scout.py --live
```
Connects to the Tello camera and overlays stella's ORB features + a live coverage%/verdict
on every frame. Carry the Tello around and point it at the floor, the mats, glass, white
walls, the stage screen. **Darkened cells = SLAM choke zones.** Find the spots that read
POOR before you ever fly -- that is where the map will break.

**From photos (quick, no Tello):**
```bash
./feature_scout.py --floor <down-shot>.jpg --forward <fwd-shot>.jpg
```

Either way: **the floor is what the VPS sees.** GOOD = worth flying; MARGINAL/POOR = run
SITL. What you see is an optimistic ceiling (the 960x720 stream is worse), so demand a
clear GOOD.

---

## Test 2 — C1: does stella track on the real Tello? (go/no-go)

Prereqs: joined to the Tello WiFi; the Tello tree and the SLAM tree are built
(`build/release/slam/bin/stella_vslam_monocular` must exist). Use a big terminal window
so tmux can lay out four panes.

```bash
cd /root/groundstation/scripts/tello/slam
./c1test.sh              # or: ./c1test.sh mats   to label the surface
```

It prints the log path, e.g. `runs/c1_20260812T143005.log`. Four panes come up: video RX,
stella, manual teleop, and the live `[TELLO_SLAM]` measurement. **Fly a path out, then a
return-to-start loop.** Detach with **Ctrl-B then D**, or **Ctrl-C** to stop.

Get the digest:

```bash
./digest.sh
```

It prints the numbers, saves `runs/<label>_<stamp>.digest.txt`, and tells you which file to
send. **Send me that `.digest.txt`.**

**GO:** verdict `PASS`, avg tracking_frac >= ~0.7, BLIND/NO-VIDEO ~0, return-to-start error
small and steady.
**NO-GO:** verdict `FAIL`, low tracking_frac, many BLIND seconds, or the drone visibly
drifts the instant SLAM drops. -> the venue floor is not SLAM-readable; run SITL.

Status: on chair mats (axistest_20260812) C1 read 100% uptime, 0 BLIND, ~27 Hz — a clean
pass, and the run that pinned the frame mapping the hover node uses (stella map is
camera-optical: +x right, +y down, +z forward).

### Physical drift in metres (the honest ground truth)

Telemetry can't measure XY drift (the Tello reports `vgx/vgy=0`, and a blind VPS reads a
false zero). So for real drift, **film the flight with a fixed phone** and run:

```bash
python3 ../measure_drift.py flight.mp4 --hfov 65 --width-m 0.18
```

That external camera sees the drone whether or not the VPS/SLAM can. Use it for the
hover-hold on-vs-off comparison once the hover node lands.

---

## Test 3 — hover-hold + land-on-loss (the SLAM position loop)

The node is `tello_slam_hold`. It owns a TelloBackend, subscribes `slam/pose` +
`slam/tracking_state`, holds the position you engage at, and lands if tracking stays lost
past a short window. Frame mapping is the C1-validated camera-optical map (see Test 2).

**Build it** (Tello backend config — the node lives in the Tello tree, not the PX4 one):

```bash
cd /root/groundstation
cmake -S . -B build/tello -DGROUNDSTATION_BUILD_EXECUTABLE=ON -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON
cmake --build build/tello --target tello_slam_hold -j
```

**Run it** — bring up the SLAM panes as in Test 2 (RX + stella publish `slam/pose` and
`slam/tracking_state`), then in a fifth pane, with `/dev/input` access:

```bash
sudo build/tello/bin/tello_slam_hold      # sudo only if not in the input group
```

Keys: `T` takeoff, `L` land, `H` engage hold (captures the current SLAM position as the
setpoint), `G` release to a plain hover, `Esc` land + quit.

**The two measurements:**

1. **Hold on vs off (drift cancelled).** Fly up over the mats, film with a fixed phone.
   First hover with `G` (hold off) for ~20 s, then `H` (hold on) for ~20 s. Run
   `../measure_drift.py` on each clip. **Good:** the hold-on drift is clearly smaller than
   hold-off. That is the whole point of the node.
2. **Land-on-loss (the safety floor).** With a hold engaged, cover the camera (or walk it
   onto glass). **Good:** the drone stops translating immediately (zero velocity), holds
   ~2 s attempting re-track, and if SLAM does not come back it lands — it never drifts
   blind. Uncover within the 2 s window and it should resume the hold.

Send me: the two drift numbers, and whether the loss test landed cleanly vs drifted.

**Not yet validated — do NOT engage a hold after a large yaw.** The ENU->body mapping
assumes the drone holds the heading it engaged at. Rotating the hold through a yaw needs
the pose quaternion convention checked first (C1 logged position only). For now: engage the
hold facing the same way you took off.

---

## Files

- `runtests.sh` — offline unit tests (Test 0).
- `feature_scout.py` — surface pre-screen (Test 1).
- `c1test.sh` / `run.sh` — C1 bring-up with a dated log (Test 2).
- `measure_tello_slam.py` — the live `[TELLO_SLAM]` measurement (SLAM-internal metrics).
- `digest.sh` — turns a C1 log into a `.digest.txt` to send back.
- `../measure_drift.py` — external-camera physical drift in metres (reused from Agent 0).
- `tello_slam_hold` (built target) — the hover-hold + land-on-loss node (Test 3); source at
  `source/llm_to_action/tello_backend/test/tello_slam_hold.cpp`.
