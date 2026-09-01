# RoboMaster S1 — interface + jailbreak field guide (2026-08-26)

Purpose: take a RoboMaster S1 from unknown state to a working video source for the
`source/integration/` perception stack. Combines the prepared notes (`FIELD_CHECKLIST.md`,
`README.md`, `hack-collabnix/`) with firmware intel sourced 2026-08-26. This unit is ours to
own; the unlock enables DJI's own EP SDK on hardware we own — standard hobbyist robotics.

---

## 0. Straight answer: what are the odds, given "~1 year old, maybe never updated"?

**Uncertain, leaning risky. "Not updated for a year" does not help much.** Here is why.

- The firmware that blocks the unlock landed around 2021 (the `00.06.05xx` line). That is ~4 years
  before a 2025 purchase. So the blocking patch predates the whole "last year" window.
- "Never updated in the last year" only tells you the firmware has not moved recently. It tells you
  nothing about what it was ALREADY on when the clock started. If it was already on `00.06.0518`
  or later a year ago, sitting untouched keeps it blocked.
- First-time activation with the RoboMaster app historically prompts a firmware update. Any unit
  paired-and-activated in the app era likely got pushed to the latest (blocked) firmware then.

**Where the odds are actually good:** a unit that was never activated (factory-sealed old stock),
or one whose owner deliberately declined every update. **Where they are bad:** any unit that was
paired, activated, and allowed to update at least once — which is most used units.

**Bottom line:** you cannot know the odds from age alone. The firmware version IS the odds. You
have to read it (off the app, or ask the seller for the exact `00.06.xxxx` number and update
history) before committing. Treat a unit you cannot get a version number for as a gamble.

---

## 1. The firmware ladder (sourced 2026-08-26)

| Version | Unlock status | Evidence |
|---|---|---|
| `00.06.0300` and earlier | **WORKS** | shipped with App v1.1.2 (~Sept 2020); community reports confirm the root works on this line |
| between `0300` and `0518` | **UNCONFIRMED** | no clean report either way — treat as risky |
| `00.06.0518` and later | **BLOCKED** | a user reported updating `00.06.0300 -> 00.06.0518` killed a working hack; "latest firmware breaks root hack" is the consistent forum consensus |

Rule of thumb on-site: **`<= 00.06.0300` = go. `>= 00.06.0518` = the software root is dead.**
Anything in between is a gamble — decide by how much you trust the fallbacks in section 6.

*Unverified:* the exact last-safe version between 0300 and 0518. Nobody published a clean boundary.
Do not trust a tighter number than this table from memory.

---

## 2. Before you commit — determine three things

1. **Is it an S1 or an EP / EP Core?** The EP ships with the SDK ENABLED. No unlock, no firmware
   trap, no risk. If the unit is an EP, sections 3–6 do not apply — skip to section 5 (interface).
2. **What firmware is it on?** Pair it in the RoboMaster app, read Settings/About. Write down the
   exact `00.06.xxxx`. Cross-check against the table in section 1.
3. **Has it ever been activated / updated?** Ask directly. Never-activated is the best case. If the
   owner says "I kept it current," assume blocked.

**Do NOT let the app update the firmware at any point.** Decline every prompt. One accepted update
can move a usable unit to a blocked version permanently.

---

## 3. Bring kit (prep BEFORE you go — no internet may be available on-site)

- Laptop, charged. **`adb` installed and on PATH** — NOT present on this workstation today; install
  it before the trip (`apt install android-tools-adb` or the platform-tools zip). The probe does
  not need adb; the unlock (section 4) does.
- The whole `source/robomaster/` folder, including `hack-collabnix/` — already cloned on disk with
  `root.py_s1`, `upload.sh`, `s1_sdk_hack.zip`, and the root PDF. Offline-ready.
- USB-C cable (robot <-> laptop, for adb + the RNDIS fallback at `192.168.42.2`).
- Phone with the RoboMaster app, logged in.

---

## 4. Step-by-step: probe, then jailbreak

### 4a. The 10-second probe — is it ALREADY unlocked? (read-only, no risk)

Set the robot to direct/AP in the app, join its Wi-Fi (SSID `RMS1-XXXXXX`), robot IP `192.168.2.1`.

```
python3 source/robomaster/s1_probe.py            # AP mode -> 192.168.2.1:40923
python3 source/robomaster/s1_probe.py 192.168.42.2   # if on USB/RNDIS instead
```

- `*** SDK MODE ENABLED ***` -> already unlocked (or it is an EP). **Stop here** — go to section 5.
- `CONNECT FAILED` / no `ok;` -> SDK is LOCKED. Continue to 4b **only if** the firmware cleared
  section 1.

### 4b. Root the S1 (only if firmware is `<= 00.06.0300`, or you accept the gamble)

Source: `hack-collabnix/` (`hack.md`, `README.md`, `How to Root - Robomaster S1.pdf`). The PDF's
original root script is DEAD — use the repo's `root.py_s1` contents instead. Steps:

1. **App -> Lab -> Python.** Paste the full contents of `hack-collabnix/root.py_s1`. Press **Run**.
   This escapes the Lab sandbox and enables ADB on the robot. (This is the exact step later
   firmware blocks — if it throws an exception here, your firmware is patched. Stop; go to 6.)
2. **From the laptop:** `adb shell` into the robot. In the shell, `cd` to the `hack-collabnix/`
   directory contents on the robot and run `./upload.sh`. This installs the EP SDK-enable payload.
   (`upload.sh` is 248 bytes — read it first so you know exactly what it does.)
3. **Power-cycle the robot** (off, then on). On boot listen for **two chimes instead of one** =
   success. One chime = it did not take.
4. **Re-probe:** `python3 source/robomaster/s1_probe.py` -> expect `*** SDK MODE ENABLED ***`.

Notes from the repo's changelog: adb is re-enabled by default (disables RNDIS — comment the adb
line in `patch.sh` if you need Ethernet-over-USB); vision module + QR scanning are confirmed
working post-unlock; both text and binary SDK protocols work.

---

## 5. Once unlocked — interface and prove video (the demo-critical path)

The S1 speaks the exact EP plaintext SDK once unlocked.

| Thing | Value |
|---|---|
| Control port (TCP) | `40923` — ASCII commands, each ends with `;`; enter SDK with `command;` -> `ok;` |
| Video (TCP) | `40921` — raw H.264, started with `stream on;` |
| IP (AP / USB) | `192.168.2.1` / `192.168.42.2` |

Test order (all in `source/robomaster/`):

```
python3 s1_probe.py    # SDK on? (read-only)
python3 s1_video.py    # does camera H.264 flow? <- THE demo-critical test
python3 s1_text.py     # SDK mode + queries, no motion (add --move only if secured)
```

**Wire video into the stack (~1 h once bytes flow).** The S1's H.264 on TCP 40921 is the same shape
as the drone feed. Fast route, zero shared-C++ change:

```
SCENE_INPUT="tcpclientsrc host=192.168.2.1 port=40921 ! h264parse ! ..." python3 scene_omdet.py
```

Clean route (the only place the standing rule allows touching shared C++): point
`llm_to_action_gstreamer_rx` at `40921` so it publishes `camera/stream`, then run scene_omdet with
`SCENE_INPUT=ros` — identical to the drone path. No fly-away risk: keep chassis motion off or wheels
off the ground; it is a camera on wheels. The VLM never drives it.

---

## 6. If the firmware is BLOCKED — the fallbacks (and why neither is a tomorrow task)

- **Firmware downgrade:** possible in principle only with the correct old firmware file in hand. S1
  firmware is signed and old files are not reliably hosted anywhere we found. Riskiest path; can
  brick the unit. **Not reliable for a deadline.**
- **CAN-bus hack** (`RoboMasterS1Challenge/robomaster_s1_can_hack`): firmware-INDEPENDENT — it
  emulates the intelligent controller over CAN with an STM32 + Raspberry Pi 4B + CAN transceiver.
  It sidesteps the Lab sandbox entirely, so patches do not matter. But it needs extra hardware and
  real integration work. **A project, not a Demo-Day step.**

---

## 7. Critical flag (owed, not a decision — you sequence)

T2's whole value is programmatic video off the S1, and that requires the unlock. For a random
~1-year-old unit with unknown firmware, the unlock is a coin-flip at best, and both fallbacks are
too heavy for tomorrow. So **T2 as a Demo-Day lever is high-variance**: it pays off big if the
firmware happens to be pre-patch, and yields nothing usable by tomorrow if it is not. T1 (the C++
FMU, already proven on the mock) carries none of that risk. Weigh T2 as the swing bet, not the
anchor. Your call on whether to chase it.
