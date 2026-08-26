# Spec — Android-in-Docker bridge feasibility (research spike)

**Type:** time-boxed feasibility spike (2-3 days). **Output:** a go/no-go report + a working
Dockerfile/setup if it works. **Owner:** a background agent. **Runs in parallel** with cleanup;
collides with nothing.

## Objective

Determine whether an **emulated Android kernel running in Docker** (redroid, or Waydroid-class)
can run the **DJI Mobile SDK (MSDK v5)** and drive a **DJI Mini 4/5 Pro** via the physical
remote controller (RC) over USB — **replacing a physical phone** in the control bridge.

If yes, our Linux stack talks to a container (over ADB/localhost) instead of a phone: cleaner,
cheaper, reproducible, no separate device.

## Why this matters

- Consumer DJI has **no desktop/Linux SDK**; MSDK v5 is **Android-only**. Some Android runtime
  is mandatory to control a Mini.
- A physical phone works but is an extra device + an awkward USB relay. A container bridge would
  be pure software on the same box.
- **A full-VM Android emulator was already judged a time-trap** (USB passthrough + MSDK integrity
  checks). Docker/redroid shares the host kernel and host devices, so it *may* clear the USB
  hurdle a VM cannot — that's the whole question.

## Known risks (these are what the spike must resolve)

1. **USB accessory passthrough of the RC into the container.** The RC enumerates as a USB
   accessory; Android's USB-host/accessory framework inside redroid/Waydroid must see it. Host
   `--device` / usbip sharing is possible; whether Android *inside* recognizes the DJI RC as the
   accessory MSDK expects is the crux.
2. **MSDK online registration/activation.** MSDK needs a DJI developer app-key + a one-time
   network activation and does device-integrity checks; some emulated environments are refused.

## Tasks

1. **Stand up redroid in Docker** (x86_64; GPU passthrough if the MSDK sample needs it). Confirm
   ADB access from the host and a working Android desktop.
2. **Install a minimal MSDK v5 app** (the official `Mobile-SDK-Android-V5` sample is fine).
   Register a DJI dev app-key; **attempt activation from inside the container.** Record whether
   MSDK activates or refuses the environment.
3. **USB passthrough of a DJI RC** (RC-N2 / RC-N3) into the container; verify Android enumerates
   it and the MSDK app reports "product connected" (an RC alone, no aircraft, is enough to test
   enumeration + the product-connected callback).
4. **If 2 + 3 pass:** with a drone available, attempt one **Virtual Stick** command + read
   **telemetry** (velocity/attitude) through the sample app, from the container.

## What can be tested WITHOUT the drone (do first)

Steps 1-3 need only a **DJI RC**, not the aircraft: container up, MSDK activates, RC enumerates,
"product connected" fires. That already answers the hard 80% (the two risks above). Step 4 (real
virtual-stick + telemetry) waits for the drone.

## Go / no-go criteria

- **GO:** MSDK activates in the container AND the RC enumerates AND the app reports the product
  connected — from Docker, no physical phone. (Bonus: virtual-stick + telemetry once the drone
  is here.)
- **NO-GO:** activation refused, or the RC cannot be enumerated inside the container after
  reasonable effort. -> Fall back to a **cheap dedicated Android device as a headless bridge**
  (documented in the mission brief); do NOT sink more than the time-box into emulation.

## Deliverable

A short report: which steps passed/failed, the blocking issue if any, and — if GO — the
Dockerfile + run commands + the ADB/localhost interface our `DroneBackend` will talk to.

## References

- redroid (Android in Docker); Waydroid (Android in a container).
- `dji-sdk/Mobile-SDK-Android-V5` (the sample + supported-products list).
- Prior finding: MSDK is Android-only; MSDK issue #670 (indoor virtual-stick, unanswered).
- Mission brief `mission-brief-2026-08-15.md` for platform context.
