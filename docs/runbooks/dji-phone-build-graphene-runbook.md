# DJI Exoskeletons app — build from VSCode + run on GrapheneOS + WiFi to the workstation

Precedes Task A of `dji-bringup-runbook.md`. Goal: compile the teammate's MSDK v5 app, install it on a
GrapheneOS phone, and let the workstation reach its ApiServer over WiFi so `DjiBackend` can drive the drone.

**Facts pulled from the repo (not guessed):**
- Gradle project root: `SampleCode-V5/android-sdk-v5-as/` (has `gradlew`). Module is `:sample`.
- Gradle **7.6.6** wrapper, AGP **7.4.2**, Kotlin 2.1.0, **NDK 21.4.7075529**, compile/target SDK **34**, minSdk 30.
- `applicationId = com.dji.sampleV5.aircraft`. **AIRCRAFT_API_KEY is already committed** in
  `SampleCode-V5/android-sdk-v5-as/gradle.properties` and is bound to that package id.
- Test keystore committed (`msdkkeystore.jks`, pw `123456`) — debug build self-signs. MSDK v5 keys are
  package-bound, not signature-bound, so the committed keystore is fine.
- GMS deps present: `play-services-location`, `mlkit:translate`, Google Maps key. **This is the only real
  GrapheneOS gotcha** (see Phase 3).
- ApiServer: Ktor CIO, `DEFAULT_API_PORT = 8080`, host `0.0.0.0`. Video `DEFAULT_STREAM_PORT = 5600`
  (matches our `kDjiVideoPort`). Cloud tunnel (`Tunneling.kt`, pinggy/cloudflare) is a **separate explicit
  call** (`ApiServerVM.startTunneling`) — it does NOT auto-start with the service. Never trigger it.

---

## Phase 0 — clone + feature branch (you run all git)
```bash
git clone https://github.com/ExoSkeletons/DJI-android-sdk-v5-recon-swarm.git ~/exoskeletons
cd ~/exoskeletons
git checkout -b feature/raw-h264-tcp
```
The branch is for the raw-H.264-over-TCP work (Phase 6). You can build + fly on it unchanged first.
No push access → fork on GitHub and `git remote add fork <your-fork-url>` before pushing.

## Phase 1 — workstation toolchain (VSCode = editor + terminal; no Android Studio needed)
Building Android from VSCode is just command-line Gradle. Install once:
```bash
# JDK 17 (AGP 7.4.2 + Gradle 7.6.6 want 11-17; use 17)
sudo apt install -y openjdk-17-jdk
# Android SDK command-line tools -> ~/android-sdk
mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
curl -o cmdtools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip cmdtools.zip && mv cmdline-tools latest
export ANDROID_HOME=~/android-sdk
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" "ndk;21.4.7075529"
```
Add the two `export` lines to `~/.bashrc`. Point the build at the SDK:
```bash
printf 'sdk.dir=%s\n' "$HOME/android-sdk" > ~/exoskeletons/SampleCode-V5/android-sdk-v5-as/local.properties
```
Optional VSCode extensions: "Kotlin Language" + "Gradle for Java" for editing. Build stays terminal-side.

## Phase 2 — build the APK
```bash
cd ~/exoskeletons/SampleCode-V5/android-sdk-v5-as
./gradlew :sample:assembleDebug
# APK lands at:
ls -la ../android-sdk-v5-sample/build/outputs/apk/debug/*.apk
```
NOTE: the module task is **`:sample:assembleDebug`** (settings.gradle names it `:sample`), not the
`:android-sdk-v5-sample:...` shown in the older bring-up runbook. **Do NOT change `applicationId`** — the
committed API key dies if the package id changes.

## Phase 3 — GrapheneOS phone prep
1. **Developer options + ADB.** Settings → About phone → tap Build number 7x. Then Settings → System →
   Developer options → enable **USB debugging**. GrapheneOS locks the USB data port when the screen is
   locked; keep the phone **unlocked** while running adb, and accept the RSA-key prompt on first connect.
2. **Sandboxed Google Play (the GrapheneOS gotcha).** The app links `play-services-location` + `mlkit`.
   Without GMS these can throw at init. GrapheneOS's blessed, no-root fix: open the **Apps** app
   (GrapheneOS's own) → install **Google Play services** (and Play Store) into this profile. It runs
   sandboxed. Do this before first launch. (Alternative: strip the GMS deps in the fork — more work; not
   needed for sticks/status/takeoff/land. Sandboxed Play is the low-effort safe path.)
3. **Install the APK** (phone on USB to the workstation, RC unplugged for now):
   ```bash
   adb devices           # confirm the phone shows up
   adb install -r ~/exoskeletons/SampleCode-V5/android-sdk-v5-sample/build/outputs/apk/debug/*.apk
   ```
   adb installs bypass the "unknown sources" UI.
4. **First launch = MSDK online activation.** The first app start validates the committed app key against
   DJI's server. Keep the phone on **internet WiFi** for that first launch; it caches afterward and runs
   offline. Grant the permission prompts (location, notifications, mic).

## Phase 4 — RC-N3 + aircraft
1. Power the drone + RC-N3. Connect the **phone to the RC-N3 by USB-C cable**. The app talks to the aircraft
   *through* the RC (OcuSync) — there is no separate drone WiFi to join.
2. Grant the Android "USB device" permission dialog when it appears.
3. In the app, confirm it shows the aircraft connected (product/firmware). This binds virtual-stick control.
   NOTE: the phone's USB-C is now taken by the RC, so the **workstation link must be WiFi** (Phase 5) —
   you cannot adb-over-USB and cable-to-RC at the same time.

## Phase 5 — WiFi: phone <-> workstation
Pick one topology (prefer **5 GHz**, per bring-up Task C):
- **Field / no router:** phone **Wi-Fi hotspot** (Settings → Network → Hotspot, 5 GHz). The workstation's
  AX210 joins it. Phone is usually `192.168.x.1`. (Do the Phase 3.4 online activation *before* switching to
  the isolated hotspot, since the hotspot has no internet.)
- **Bench:** put phone + workstation on the same router/AP SSID.

Then from the workstation:
```bash
# find the phone IP (over adb/USB, or from the router/hotspot list):
adb shell ip -f inet addr show wlan0     # or ap0 when hotspotting
# start the ApiServer bound to all interfaces on 8080 (do it from the app UI, host 0.0.0.0 port 8080)
curl http://<PHONE_IP>:8080/status/      # expect the aircraft JSON
```
**Safety:** never invoke the tunnel action (`startTunneling`) — the challenge is local, and a relay
round-trip blows the <1 s budget. Only start the plain service.

Once `/status/` returns JSON, jump to `dji-bringup-runbook.md` Task B (soak test + latency probe against
`<PHONE_IP> 8080`).

## Phase 6 — the raw-H.264-TCP change (on feature/raw-h264-tcp)
`VideoTcpServer.kt` already opens a `ServerSocket` on `DEFAULT_STREAM_PORT = 5600` and pushes H.264/H.265
NAL via `ICameraStreamManager` — but `ApiServer.kt` only wires the **RTMP** path (`POST /c/stream/start`).
The branch's job: add routes that start/stop the TCP streamer, e.g. `POST /c/video/start` ->
`VideoTcpServer.start(streamPort)` and `POST /c/video/stop`. That matches our `kDjiVideoPort=5600` and the
`gst-launch-1.0 tcpclientsrc host=<PHONE_IP> port=5600 ! decodebin ! ...` eyeball decode in the bring-up
runbook. Coordinate the exact route name + codec with the app author, then PR it back.
