# Exoskeletons repo — Android Studio bring-up (handoff)

Audience: an agent (or Android dev) getting the DJI MSDK v5 sample app building + running in
Android Studio. Written 2026-08-22. Facts verified against the repo, not guessed.

## What this repo is
DJI MSDK v5 sample app (Kotlin + Ktor). Runs on a GrapheneOS phone; talks to the DJI drone via
the RC-N3 over USB-C. It exposes, on the phone, for the Linux workstation over WiFi:
- `:8080` HTTP + WebSocket — control, telemetry, and **`POST /tts`** (the phone speaks the
  workstation's perception answers via Android TextToSpeech / `TTSManager`).
- `:5600` raw H.264 TCP — low-latency video.
The workstation is the brain; the phone is the bridge to the drone AND the mouth (TTS + on-phone
Vosk STT). MSDK key is committed and bound to the applicationId.

## THE fix for "no run configuration" (this is the usual cause)
The Gradle project root is NOT the repo root. Open EXACTLY:

    SampleCode-V5/android-sdk-v5-as/        <- has settings.gradle + gradlew

Its `settings.gradle` wires two modules that live BESIDE it:
- `:sample`  -> ../android-sdk-v5-sample   (the app; applicationId com.dji.sampleV5.aircraft)
- `:uxsdk`   -> ../android-sdk-v5-uxsdk

Open the repo root or the `-sample` folder instead and AS never finds `settings.gradle`, never
syncs as a Gradle project, and never generates a run config. After a clean sync, a run
configuration named **sample** appears automatically. Select it -> Run.

## Toolchain is PINNED — mismatch = silent sync failure = no run config
- Gradle 7.6.6 (wrapper), AGP 7.4.2, Kotlin via $KOTLIN_VERSION, compileSdk/targetSdk 34, minSdk 30.
- **Gradle JDK MUST be 17** (11 works too). JDK 21 does NOT run Gradle 7.6 -> sync fails.
  Set: Settings -> Build, Execution, Deployment -> Build Tools -> Gradle -> Gradle JDK = 17.

## local.properties ships WRONG (committed by mistake)
`android-sdk-v5-as/local.properties` = `sdk.dir=/root/android-sdk` (a container path). On your
machine: delete it (AS regenerates on open) or set `sdk.dir=/home/<you>/Android/Sdk`. A stale
sdk.dir gives "SDK location not found" and blocks sync.

## Do NOT change these
- applicationId `com.dji.sampleV5.aircraft` is bound to the committed DJI MSDK API key. Renaming
  it invalidates the key -> MSDK won't activate.
- API keys come from `gradle.properties` (AIRCRAFT_API_KEY, GMAP_API_KEY) via manifestPlaceholders.
  Leave gradle.properties as-is.
- First launch needs internet ONCE so the MSDK activates the key. After that it runs fully local.

## Build / install
- In AS: select the `sample` run config -> Run (phone in USB debugging).
- CLI (no AS): `SampleCode-V5/android-sdk-v5-as/gradlew :sample:assembleDebug`, then `adb install`.
- Or use the repo's `tools/adk.sh` task runner (setup/build/install/status/video).

## GrapheneOS
The app pulls Google Play Services / ML Kit / Maps (NOT on the control path). Install
**sandboxed Google Play**; change no code. A Google-init crash on first launch = install that.

## If you edit the container copy: commit BEFORE the bind-mount
If ~/workspaces/exoskeletons will be bind-mounted over the container's /root/exoskeletons,
commit + push any container-side changes FIRST or the mount shadows and loses them.
