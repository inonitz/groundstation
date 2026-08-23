# Post-PoC cleanup — GrapheneOS phone + demo hacks (revert after Thursday)

Written 2026-08-23. These are throwaway scaffolding for the Thursday demo. Nuke after.
Real destination is on-phone Vosk (offline, no Google). See TODO at the bottom.

## Why any of this exists
GrapheneOS has no voice recognition service. The app's `SpeechResolversVM` calls Android
`SpeechRecognizer`, which needs a system `RecognitionService`. There was none, so STT threw
`ERROR_CLIENT`. To demo fast we installed Google's speech service and forced the pipeline to
English. All of it is disposable.

## What changed (two places)

### 1. Code — VoiceControlFragment.kt (4 lines, uncommitted)
Forced the voice pipeline to English so STT, the command matcher, and the action resolver agree.
- lines 74, 81: app locale `he-IL` -> `en-US` (loads default English command strings)
- line 134: action resolver lang `listOf("he")` -> `listOf("en")`
- line 150: STT request locale -> `Locale("en", "US")`

### 2. Phone — Google speech service + setting
- Installed "Speech Recognition & Synthesis from Google" (`com.google.android.tts`) via sandboxed Play.
- Set secure `voice_recognition_service` to the Google component.
- Google downloaded the `en-US` offline model (lives inside `com.google.android.tts` app data).

## Nuke steps

Paths assume adb at `~/Apps/AndroidSDK/platform-tools/adb` and repo at
`/home/swapgs/workspaces/DJI-android-sdk-v5-recon-swarm`.

### Revert the code (run git yourself)
    cd /home/swapgs/workspaces/DJI-android-sdk-v5-recon-swarm
    git checkout -- SampleCode-V5/android-sdk-v5-sample/src/main/java/com/kcg/dr/voice/VoiceControlFragment.kt
If the change was committed by demo time, revert that commit instead of checkout.

### See what Google stuff is on the phone
    ~/Apps/AndroidSDK/platform-tools/adb shell pm list packages | grep -iE "google|vending|gms|gsf"

### Remove it (speech app first, Play core last)
    ADB=~/Apps/AndroidSDK/platform-tools/adb
    $ADB shell pm uninstall --user 0 com.google.android.tts     # also deletes the downloaded en-US model
    $ADB shell pm uninstall --user 0 com.android.vending        # Play Store
    $ADB shell pm uninstall --user 0 com.google.android.gms     # Play Services
    $ADB shell pm uninstall --user 0 com.google.android.gsf     # only if listed above

### Clear the setting and reboot
    $ADB shell settings delete secure voice_recognition_service
    $ADB shell reboot

### Verify clean
    ~/Apps/AndroidSDK/platform-tools/adb shell pm list packages | grep -iE "google|vending|gms" || echo "clean"

## Do NOT nuke (legit setup, not demo hacks)
- Extracted `~/.m2` llamacpp repo (the `com.llama.cpp.android:lib:1.0.0` artifact from m2.zip).
- `local.properties` (machine-specific SDK path).
Deleting either just re-breaks the build.

## TODO — the real fix (post-Thursday, with llm_to_action work)
On-phone STT should be Vosk, not Google. It is already half-built:
- `VoskSpeechRecognizer.kt` exists and `libvosk.so` is in the APK, but the class is ORPHANED —
  nothing instantiates it. `SpeechResolversVM` hardwires Android `SpeechRecognizer`.
- No model assets. `VoskSpeechRecognizer` reads `assets/models/<lang>/`; only `flysafe`/`mop`
  exist under assets. Need a Vosk English model in `assets/models/en/`.
Wire `VoskSpeechRecognizer` into `SpeechResolversVM` (feed onPartial/onSpeechEnded into the
existing `_partialSpeech`/`_speech` LiveData) and drop in the model. Then no Google, no `he-IL`
problem, fully offline.
