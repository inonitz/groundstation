# source/robomaster — S1 as a platform-agnostic CV target

_Legitimacy: this enables DJI's own documented developer SDK on a consumer RoboMaster we own — standard hobbyist robotics (widely published community unlock), not a security exploit against any third party._

**What this is for:** point the *existing* `source/integration/` perception stack at the
RoboMaster S1's camera to prove "same brain, different platform." Video-in only, per the
recorded scope (ROADMAP "LAND PLATFORM ASSESSMENT"). No autonomous ground control.

**Status:** UNVERIFIED end to end. Scripts here are written against the documented plaintext
SDK; none has been run against a real S1 (we don't have one yet). Treat every VERDICT the
scripts print as the real test.

---

## THE ONE THING THAT DECIDES EVERYTHING: is SDK mode on?

The S1 ships with the plaintext SDK **disabled**. The EP ships with it **enabled**. DJI never
gave S1 owners the SDK officially, so the S1 needs a community **root/unlock** to turn it on.

- **Already unlocked** (seller did it, or you do it) -> the S1 speaks the exact same text
  protocol as the EP on TCP **40923**, and streams H.264 on **40921**. `s1_probe.py` tells you
  in 10 seconds.
- **Locked** -> port 40923 refuses. You must root it first.

---

## FIRMWARE TRAP (the make-or-break, and the part I could NOT fully verify)

- The community unlock relies on a Python sandbox escape in the app's "Lab". **DJI patched it in
  later firmware.** The hack guides say plainly: **"Do not update to the latest version, as it
  may block the hack."**
- **I could not extract the exact safe-vs-blocked firmware version numbers** from the sources in
  the time I had. DO NOT trust a version number from memory here — a wrong one wastes the trip.
  **On-site, READ the version off the app and ask the seller its update history BEFORE paying.**
  The safe move: a unit that has *never been updated*.
- Downgrade is possible in principle (flash an older firmware) but is the riskiest path and needs
  the correct old firmware file in hand. If the unit is already on latest and you have no
  downgrade file, treat it as NO-GO for today.

---

## UNLOCK PROCEDURE (do this at home if the unit is stock but compatible)

Source: `collabnix/robomaster` (hack.md) and `sgrsn/robomaster-python-hack`. Do this yourself
against the repo files — I am NOT reproducing the root payload from memory (wrong bytes = bricked
robot). Clone the repo and use ITS files:

1. **Clone the unlock repo** (do this NOW, before you leave — no internet needed at the house):
   ```
   git clone https://github.com/sgrsn/robomaster-python-hack
   # and/or
   git clone https://github.com/collabnix/robomaster
   ```
   Read `How to Root - Robomaster S1.pdf` in the repo. NOTE: the PDF's original root script is
   dead — **use the repo's `root.py_s1` file contents as the root script instead.**
2. In the RoboMaster app: **Lab -> Python**, paste the `root.py_s1` contents, **Run**. This
   escapes the sandbox and enables ADB on the robot.
3. `adb` from the laptop: `adb shell` into the robot. `cd` to the extracted repo dir, run
   `./upload.sh`. This installs the SDK-enable payload.
4. **Power cycle.** On boot you should hear **two chimes instead of one** = success.
5. Re-run `python3 s1_probe.py` -> expect `*** SDK MODE ENABLED ***`.

---

## ONCE UNLOCKED — the text API (this is the "1 hour" path)

Plaintext SDK, confirmed from the RoboMaster Developer Guide:

| Thing | Value |
|---|---|
| Connection: direct/AP | join robot Wi-Fi, robot IP **192.168.2.1** |
| Connection: USB/RNDIS | robot IP **192.168.42.2** |
| Connection: router/STA | robot gets DHCP IP; discover via UDP broadcast on **40926** |
| Control port (TCP) | **40923** — send ASCII commands, each ends with `;` |
| Enter SDK mode | send `command;` -> robot replies `ok;` |
| Video (TCP) | **40921**, raw H.264, started with `stream on;` |
| Audio / telem / event | 40922 / 40924 / 40925 |

Test order at the house (all in this folder):
1. `python3 s1_probe.py`  — is SDK on? (read-only)
2. `python3 s1_video.py`  — does camera H.264 flow? (**this is the demo-critical one**)
3. `python3 s1_text.py`   — SDK mode + queries, no motion. Add `--move` (gimbal) only if secured.

### Wiring video into the demo (the actual integration, ~1h once video flows)
The S1's H.264 on TCP 40921 is the same shape as the drone feed. Two routes:
- **Fast/manual:** `SCENE_INPUT="tcpclientsrc host=192.168.2.1 port=40921 ! h264parse ! ..."`
  straight into `scene_omdet.py` (it already takes a GStreamer `SCENE_INPUT`).
- **Clean:** point `llm_to_action_gstreamer_rx` at 40921 so it publishes `camera/stream`, and run
  scene_omdet with `SCENE_INPUT=ros` — identical to the drone path. The gstreamer_rx node is
  platform-agnostic on the source, so this should "just work" with the right host/port.

There is **no drone-safety fly-away risk** with the S1: keep chassis motion off (or wheels off
the ground) and it's a camera on wheels. The VLM still never drives it.

---

## robomaster_sim (answer to "what is it")
`github.com/jeguzzi/robomaster_sim` — a community **simulator** that emulates the RoboMaster
SDK/robot, so you can develop the video-in + text-API code with **no hardware**. Useful only for
writing/checking the integration before the unit is in hand; irrelevant once you have a real S1
in front of you today. Skip it if the unit works.

---

## Sources
- Unlock: collabnix/robomaster (hack.md), sgrsn/robomaster-python-hack, Hackaday "DJI RoboMaster S1 Hacks".
- Text SDK: RoboMaster Developer Guide `text_sdk/connection.html` (ports, `command;`, IPs), dji-sdk/RoboMaster-SDK.
- Sim: jeguzzi/robomaster_sim.
