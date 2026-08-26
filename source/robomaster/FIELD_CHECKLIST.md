# S1 @ SELLER'S HOUSE — 2-MINUTE CHECKLIST (print / phone this)

**Goal today: decide if this S1 is worth buying, and if it's already usable.**

## BEFORE MONEY CHANGES HANDS
1. **Power on.** Two chimes on boot = already rooted/unlocked (BEST case — pay more if so).
   One chime = stock.
2. **Open the RoboMaster app**, pair the robot. Note the **firmware version**
   (app → Settings/□ → About). WRITE IT DOWN.
3. **DO NOT let the app update the firmware.** Decline any update prompt. Latest firmware
   BLOCKS the unlock. (Source: collabnix hack — "Do not update to the latest version.")
4. **Ask the seller point-blank:** "Is the SDK unlocked / has it been rooted?" and
   "What firmware is it on, and has it ever been updated?"

## THE 10-SECOND TEST (laptop, on the robot's Wi-Fi)
- Set the robot to **direct/AP connection** in the app, then join its Wi-Fi hotspot
  (SSID like `RMS1-XXXXXX`). Robot IP is then **192.168.2.1**.
- Run:  `python3 s1_probe.py`
  - `*** SDK MODE ENABLED ***`  -> already unlocked. Then run `s1_video.py` — if video
     flows, this unit is TURNKEY. Buy it.
  - `CONNECT FAILED` / no `ok;`  -> SDK is LOCKED. Buyable only if firmware is unlock-compatible
     (see README "FIRMWARE TRAP"). If seller already updated to latest, walk away or negotiate hard.

## BRING
- [ ] Laptop, charged. `adb` installed and working (`adb version`).
- [ ] This whole `source/robomaster/` folder, **plus the cloned unlock repo** (README step 1).
- [ ] USB-C cable (robot <-> laptop, for adb + RNDIS fallback 192.168.42.2).
- [ ] Phone with the RoboMaster app, logged in.
- [ ] Small screwdriver? (some rooting guides want the unit powered + tilted; usually not needed.)

## GO / NO-GO
- **GO (turnkey):** two chimes OR `s1_probe.py` says ENABLED + `s1_video.py` shows bytes.
- **GO (needs work, ~1h at home):** stock, firmware NOT updated to latest, unlock repo in hand.
- **NO-GO:** firmware on latest with no downgrade file, OR won't connect to app at all.
