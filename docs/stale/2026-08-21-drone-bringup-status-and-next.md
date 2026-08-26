# Drone bring-up — bootstrapped state + next objective (2026-08-21)

## Status: BOOTSTRAPPED (drone + full app stack live)
- **Drone flies.** Verified with DJI Fly and the MSDK sample's Virtual Stick screen.
- **App built from source + installed** on the GrapheneOS Pixel 8 Pro. App = **MSDK Aircraft**
  (`com.dji.sampleV5.aircraft`); "LeakCanary" is a debug-only companion icon, ignore it.
- **Build env** lives in the `swapgs` container (JDK17 + Android SDK/NDK 21.4 + gradle 7.6.6). The
  clone is `/root/exoskeletons` (branch `feature/raw-h264-tcp`). The human's VSCode is remoted into
  this same container, so the built APK (`.../apk/debug/sample-debug.apk`, ~235 MB) is already on the box.
- **Missing dep resolved:** `com.llama.cpp.android:lib:1.0.0` (dev's on-phone LLM) is not committed;
  the dev's `m2.zip` was unzipped into `~/.m2` so `mavenLocal()` resolves it.
- **4 pre-existing `main` compile bugs patched** (working tree only, NOT committed): `ApiServer.kt`
  `FlyTo/LookAt::class.serializer()` -> companion `.serializer()`; `VirtualStickFragmentVoCom.kt`
  `startRecord/stopRecord` stale callback args dropped. These are the dev's bugs; report to them.
- **adb-over-container works.** USB passthrough is fine (phone visible in sysfs), but the container's
  `/dev/bus/usb` is a static snapshot -- every phone re-enumeration bumps the devnum and orphans the
  node. `tools/adbfix.sh` recreates the current node + restarts adb. Authorization ("always allow")
  persists via the adb key; only the node needs recreating after a reconnect.

## KEY FINDING: start the server from the isolated "API Server" screen, NOT "Recon Swarm (Fragmented)"
The Fragmented screen embeds the API-server toggle **with** TTS + Qwen panels; those crash, so the
server never starts. The example list already has a standalone **"API Server"** entry
(`R.id.api_server` -> `ApiServerFragment`) whose service path (`ApiServerService`/`ApiServerVM`) has
**no TTS/Qwen**. Open that, flip the toggle -> control server on **8080** + raw-H264 video on **5600**.
(The dev lacks isolated test cases for TTS and Qwen -- a place we can help later.)

## NEXT OBJECTIVE: send/receive commands to the drone through the workstation
1. Phone: open **API Server** screen, toggle ON (aircraft connected via RC-N3).
2. Workstation (swapgs): `bash /root/exoskeletons/tools/adbfix.sh` (get adb `device`), then tunnel
   over USB -- no WiFi needed:
   `adb forward tcp:8080 tcp:8080 && adb forward tcp:5600 tcp:5600`
3. Verify telemetry: `curl http://127.0.0.1:8080/status/` -> aircraft JSON.
4. Drive the real link with the existing C++ tools (already compiled this session):
   `/tmp/dji_backend_mock_test 127.0.0.1 8080 60` (soak: arm/stream/hold/land) and
   `/tmp/dji_latency_probe 127.0.0.1 8080 30 8` -> fill the latency table in `dji-bringup-runbook.md`.
   **SAFETY: props off / tethered for the first armed command; confirm WiFi/USB-loss hover-brake.**
5. Milestone: command->action p95 < 1 s on the real link => control spine demo-valid ->
   feature-total-integration simple mode.
6. **Yaw:** units/sign already fixed in `dji_backend_base.hpp` (rad/s->deg/s, ENU CCW+ -> DJI CW+,
   clamp 100 deg/s). Bench-verify the physical turn direction props-off before any in-flight yaw.

## Open items for the dev
- Isolated test harnesses for TTS and Qwen (they have none).
- 16 KB page alignment: cosmetic on the phone's default 4 KB pages; needs a newer NDK/AGP only if the
  phone is switched to 16 KB mode.
