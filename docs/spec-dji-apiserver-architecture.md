# DJI recon-swarm Android app - API server architecture

The phone app hosts the REST and WebSocket API that the ground station calls. It is a Ktor CIO
server bound to `0.0.0.0:8080`, plus a separate raw TCP video server on `5600`. Every route is
gated: the server answers `503` unless the RC, the flight controller and the product all report
connected.

Repository read: `/root/DJI-android-sdk-v5-recon-swarm` (read-only, nothing modified).
All citations below are relative to
`SampleCode-V5/android-sdk-v5-sample/src/main/java/com/kcg/dr/`, written as `app/`.

## Contents

| Section | Content |
|---|---|
| [Diagrams](#diagrams) | Simplified and detailed architecture pictures |
| [Ports and lifecycle](#ports-and-lifecycle) | Where the ports come from |
| [Connection gates](#connection-gates) | The two 503 checks |
| [Routes](#routes) | Every HTTP route and WebSocket |
| [Speech path](#speech-path) | Microphone to action |
| [TTS path](#tts-path) | Text to speaker |
| [Video path](#video-path) | Camera to ground station |
| [DJI MSDK v5 calls](#dji-msdk-v5-calls) | The SDK surface actually used |
| [Corrections to the ground-station assumptions](#corrections-to-the-ground-station-assumptions) | Where the brief was wrong |
| [Not verified](#not-verified) | Open items |

## Diagrams

![Simplified architecture](assets/dji-apiserver-simplified.png)

![Detailed architecture](assets/dji-apiserver-detailed.png)

Sources: `assets/dji-apiserver-simplified.dot`, `assets/dji-apiserver-detailed.dot`.
SVG versions sit beside the PNGs.

## Ports and lifecycle

| Item | Value | Citation |
|---|---|---|
| Default host | `0.0.0.0` | `app/api/server/ApiServerService.kt:21` |
| API port | `8080` | `app/api/server/ApiServerService.kt:22` |
| Video stream port | `5600` | `app/api/server/ApiServerService.kt:23` |
| HTTP engine | Ktor `embeddedServer(CIO, ...)` | `app/api/server/ApiServer.kt:131` |
| Owner | `ApiServerService`, a foreground Service | `app/api/server/ApiServerService.kt:26,44` |
| Start point | `onStartCommand` starts both servers | `app/api/server/ApiServerService.kt:54,56` |
| UI toggle | "API Server" screen switch | `app/api/server/ApiServerFragment.kt:50` |
| Public tunnel | Cloudflared quick tunnel to `127.0.0.1:8080` | `app/api/Tunneling.kt:88,230`; started at `app/api/server/ApiServerVM.kt:110` |

The service is `START_STICKY` (`app/api/server/ApiServerService.kt:59`). The stream port is never
overridden by an intent extra; only `HOST` and `PORT` are read
(`app/api/server/ApiServerService.kt:48-49`).

## Connection gates

There are two gates, not one.

**Gate A - global.** A routing intercept runs before every handler. It checks three DJI keys in
order and answers `503` on the first failure.

| Check | Key | Response body | Citation |
|---|---|---|---|
| Remote controller | `RemoteControllerKey.KeyConnection` | `No connection to Remote Controller` | `app/api/server/ApiServer.kt:164-169` |
| Aircraft | `FlightControllerKey.KeyConnection` | `No connection to Aircraft` | `app/api/server/ApiServer.kt:172-175` |
| Product | `ProductKey.KeyConnection` | `Product not connected` | `app/api/server/ApiServer.kt:177-180` |

The intercept is installed on the `routing { }` node (`app/api/server/ApiServer.kt:159`). Every
route below inherits it, including the WebSocket upgrade requests.

**Gate B - `/c` only.** A second intercept on the `/c` route answers `503` with
`AircraftController not initialized.` when the controller object is null
(`app/api/server/ApiServer.kt:397-406`).

## Routes

`503 gate` column: **A** means the global gate applies. **A+B** means the `/c` controller gate also
applies.

| Method | Path | Handler | What it does | 503 gate |
|---|---|---|---|---|
| GET | `/` | `app/api/server/ApiServer.kt:152` | HTML banner with host and port | A |
| GET | `/status` | `app/api/server/ApiServer.kt:268` | isFlying, battery, velocity, position, attitude, gimbal attitude, product and RC firmware | A |
| GET | `/status/battery` | `app/api/server/ApiServer.kt:307` | voltage, capacity, remaining, percent | A |
| GET | `/status/gps` | `app/api/server/ApiServer.kt:325` | satellite count, signal level, valid flag, compass heading | A |
| GET | `/status/signal` | `app/api/server/ApiServer.kt:345` | AirLink connection, quality, frequency band, band range | A |
| POST | `/tts` | `app/api/server/ApiServer.kt:186` | speaks `text` in `lang`/`country` through `TTSManager` | A |
| POST | `/key` | `app/api/server/ApiServer.kt:252` | raw DJI key get / set / action passthrough | A |
| GET | `/(fly\|takeoff)` | `app/api/server/ApiServer.kt:367` | direct `KeyStartTakeoff`; refuses if already flying | A |
| GET | `/land` | `app/api/server/ApiServer.kt:380` | direct `KeyStartAutoLanding` | A |
| GET | `/c/` | `app/api/server/ApiServer.kt:414` | controller readiness probe | A+B |
| POST | `/c/flyTo` | `app/api/server/ApiServer.kt:415` | `flyToSticks(target, maxVelocity)` to a GPS target | A+B |
| POST | `/c/lookAt` | `app/api/server/ApiServer.kt:431` | `lookAtWithSpin(target, height)` | A+B |
| POST | `/c/fly` | `app/api/server/ApiServer.kt:443` | decodes a JSON array of `Action` and runs them in order; a bare object is accepted as one action | A+B |
| POST | `/c/stop` | `app/api/server/ApiServer.kt:455` | `controller.stop()`, emergency by default | A+B |
| POST | `/c/takeoff` | `app/api/server/ApiServer.kt:459` | `controller.fly { takeoff() }` | A+B |
| POST | `/c/land` | `app/api/server/ApiServer.kt:463` | `controller.fly { land() }` | A+B |
| GET | `/c/(wave\|hi\|hey\|hello)` | `app/api/server/ApiServer.kt:468` | wave gesture | A+B |
| POST | `/c/stream/start` | `app/api/server/ApiServer.kt:474` | starts the RTMP live stream at `rtmpUrl` | A+B |
| POST | `/c/stream/stop` | `app/api/server/ApiServer.kt:491` | stops the RTMP live stream | A+B |
| GET | `/c/stream/status` | `app/api/server/ApiServer.kt:501` | `isStreaming` and live-stream status | A+B |
| WS | `/c/ws/sticks` | `app/api/server/ApiServer.kt:214`, session at `:512` | each text frame is a `FlightParam` JSON; forwarded to `sendFlightParam` | A+B |
| WS | `/c/ws/gimbal` | `app/api/server/ApiServer.kt:218`, session at `:542` | each text frame is a `GimbalRotation` JSON; forwarded to `angleCamera` | A+B |
| WS | `/c/ws/telemetry` | `app/api/server/ApiServer.kt:222`, session at `:572` | server push of location, attitude, battery, velocity and gimbal attitude | A+B |
| WS | `/c/ws/echo` | `app/api/server/ApiServer.kt:201` | diagnostic echo; closes on `bye`, `x` or `stop` | A+B |

`FlightParam` fields are `vx`, `vy`, `vz`, `yaw`, all optional doubles
(`app/flight/AircraftController.kt:245-249`). `GimbalRotation` fields are `pitch`, `yaw`, `roll`,
`duration`, `mode` (`app/flight/AircraftController.kt:274-280`).

`/c/fly` accepts these action names (`@SerialName` values in `app/api/dto/actions/`):
`takeoff`, `land`, `delay`, `fly_gps`, `fly_by`, `fly_circle`, `fly_square`, `scan_ground`,
`spin_by`, `wave`, `look_at`, `gimbal_pitch`, `home`, `follow_me`, `track_me`, `report_status`.

Command serialisation happens in `AircraftController.fly` (`app/flight/AircraftController.kt:458`).
It cancels the previous flight job, joins it, then launches the new one. Only one flight job runs
at a time.

## Speech path

The recogniser is Google's on-device `android.speech.SpeechRecognizer`
(`app/voice/SpeechResolversVM.kt:98`). It is started with `LANGUAGE_MODEL_FREE_FORM`, partial
results on, 700 ms complete-silence and 1000 ms possibly-complete-silence
(`app/voice/SpeechResolversVM.kt:289-311`). A media-button press toggles listening
(`app/voice/SpeechResolversVM.kt:188-191`).

Resolvers run in order and the first match wins (`app/voice/SpeechResolversVM.kt:334-370`). Two are
registered (`app/voice/VoiceControlFragment.kt:56-69`):

1. `RegexCommandResolver` - matches on the phone (`app/voice/SpeechResolving.kt:113-124`).
2. `GroundStationSpeechResolver` - the fallback (`app/voice/GroundStationSpeechResolver.kt:17`).

The regex patterns are Android string resources. English literals live in
`SampleCode-V5/android-sdk-v5-sample/src/main/res/values/strings.xml`.

| Command | Regex | Action | Citation |
|---|---|---|---|
| stop | `stop\|halt\|quit\|end` | `controller.stop()` | `values/strings.xml:526`, wired at `app/voice/VoiceControlFragment.kt:94` |
| takeoff | `takeoff\|take off\|fly\|sky\|liftoff\|wakeup\|sunshine\|morning` | `fly { takeoff() }` | `values/strings.xml:527`, `app/voice/VoiceControlFragment.kt:95` |
| land | `land\|landing\|ground\|down\|fall\|perch\|floor\|shutdown\|...` | `fly { land() }` | `values/strings.xml:528`, `app/voice/VoiceControlFragment.kt:96` |
| spin | `spin\|((spin\|look) around)` | `spinBy(360, 120)` | `values/strings.xml:561`, `app/voice/VoiceControlFragment.kt:100` |
| scan | `scan(?:\s+(.+))?` | `ScanGround(velocity=2.0)` | `values/strings.xml:542`, `app/voice/VoiceControlFragment.kt:102` |
| recon | `reconnaissance\|recon` | ascend 4.5 m, scan, descend | `values/strings.xml:544`, `app/voice/VoiceControlFragment.kt:105` |
| hello | `hello\|(\b(hi\|heya\|hiya\|hey\|wave)\b)` | `fly { wave() }` | `values/strings.xml:557`, `app/voice/VoiceControlFragment.kt:113` |
| silence | `stealth\|quiet\|silence\|dark` | mutes TTS | `values/strings.xml:563`, `app/voice/VoiceControlFragment.kt:115` |
| battery | `battery status\|battery\|battery level` | speaks the battery percent | `values/strings.xml:540`, `app/voice/VoiceControlFragment.kt:116` |
| return home | `return home\|(come\|go\|return)( back)?( to)? (me\|us\|base\|home)\|...` | `FlyToMe()` | `values/strings.xml:530`, `app/voice/VoiceControlFragment.kt:124` |
| follow me | `follow me\|follow (me\|us)` | `FollowMe(6.0, 3.0, 3.0)` | `values/strings.xml:532`, `app/voice/VoiceControlFragment.kt:127` |
| look at me | `looking at you\|(look\|watch\|track)( at)? (me\|us)\|...` | `TrackMe()` | `values/strings.xml:533`, `app/voice/VoiceControlFragment.kt:140` |

A Hebrew resource set carries the same commands at `res/values-iw/strings.xml:19-61`.

If no regex matches, `GroundStationSpeechResolver` runs. It translates Hebrew to English with ML Kit
(`app/voice/GroundStationSpeechResolver.kt:58-60`, stage at `app/voice/SpeechResolving.kt:226`).
It then sends the text twice. First `POST http://<gs>:8080/input` with body `{"text": ...}`
(`app/voice/GroundStationSpeechResolver.kt:46-49`). Second the same JSON over a raw TCP socket
(`app/voice/GroundStationSpeechResolver.kt:55`).

The ground-station address is discovered by a subnet scan of the hotspot interface. The first device
found wins (`app/voice/VoiceControlFragment.kt:166-193`). The port defaults to `8080`
(`app/voice/GroundStationSpeechResolver.kt:26`).

## TTS path

`TTSManager` is a singleton wrapping `android.speech.tts.TextToSpeech`
(`app/managers/TTSManager.kt:17,32`). It prefers the `com.google.android.tts` engine
(`app/managers/TTSManager.kt:20`). `speak` sets the locale, sets rate `1.3`, plays a notify sound,
then queues the utterance with `QUEUE_ADD` (`app/managers/TTSManager.kt:93-108`).

`POST /tts` takes `{text, lang, country, rate}` (`app/api/dto/TTSRequest.kt:10-15`) and calls
`TTSManager.speak` (`app/api/server/ApiServer.kt:186-192`). The `rate` field is parsed but never
applied. The handler passes only the text and the locale.

## Video path

The phone is the **server**. The ground station connects to it.

| Item | Value | Citation |
|---|---|---|
| Transport | TCP `ServerSocket` | `app/api/VideoTcpServer.kt:59` |
| Port | `5600` | `app/api/server/ApiServerService.kt:23`, passed at `:56` |
| Frame source | `MediaDataCenter.getInstance().cameraStreamManager` | `app/api/VideoTcpServer.kt:17` |
| Hook | `ICameraStreamManager.ReceiveStreamListener` | `app/api/VideoTcpServer.kt:27`, registered at `:61` |
| Camera index | `ComponentIndexType.LEFT_OR_MAIN` (default argument) | `app/api/VideoTcpServer.kt:52` |
| Framing | none; `out.write(data, offset, length)` straight to the socket | `app/api/VideoTcpServer.kt:35` |
| Clients | one at a time; a new client closes the previous one | `app/api/VideoTcpServer.kt:74` |
| Socket options | `tcpNoDelay = true`, `keepAlive = true` | `app/api/VideoTcpServer.kt:70-71` |
| Accept thread | single-thread executor | `app/api/VideoTcpServer.kt:63` |

There is no RTP layer, no MPEG-TS layer and no MTU constant. The codec is logged once from
`info.mimeType` (`app/api/VideoTcpServer.kt:30`).

## DJI MSDK v5 calls

| Purpose | Call | Citation |
|---|---|---|
| Takeoff | `FlightControllerKey.KeyStartTakeoff` | `app/flight/dji/DJIAircraft.kt:49`; also direct at `app/api/server/ApiServer.kt:374` |
| Land | `FlightControllerKey.KeyStartAutoLanding` | `app/flight/dji/DJIAircraft.kt:56`; also direct at `app/api/server/ApiServer.kt:382` |
| Confirm land | `FlightControllerKey.KeyConfirmLanding` | `app/flight/dji/DJIAircraft.kt:72` |
| Emergency stop | `KeyStopAutoLanding`, `KeyEmergencyStop`, `KeyStopTakeoff` | `app/flight/dji/DJIAircraft.kt:91,92,94` |
| Enable virtual stick | `VirtualStickManager.enableVirtualStick` | `app/flight/dji/DJIVirtualStick.kt:70` |
| Advanced mode | `setVirtualStickAdvancedModeEnabled(true)` | `app/flight/dji/DJIVirtualStick.kt:83` |
| Send sticks | `sendVirtualStickAdvancedParam` | `app/flight/dji/DJIVirtualStick.kt:142` |
| Disable virtual stick | `VirtualStickManager.disableVirtualStick` | `app/flight/dji/DJIVirtualStick.kt:106` |
| Stick control mode | RollPitch `VELOCITY`, Vertical `VELOCITY`, Yaw `ANGULAR_VELOCITY`, frame `BODY` | `app/flight/dji/DJIVirtualStick.kt:133-137` |
| Gimbal rotate | `GimbalKey.KeyRotateByAngle` | `app/flight/dji/DJIGimbal.kt:94` |
| Gimbal mode and reset | `GimbalKey.KeyGimbalMode`, `KeyGimbalReset` | `app/flight/dji/DJIGimbal.kt:30,45` |
| RC stick listeners | `RemoteControllerKey.KeyStickLeft*`, `KeyStickRight*` | `app/flight/dji/DJIRCStick.kt:16-35` |
| Telemetry listeners | `KeyIsFlying`, `KeyAreMotorsOn`, `KeyAircraftLocation3D`, `KeyAircraftVelocity`, `KeyAltitude`, `KeyBatteryPowerPercent`, `KeyAircraftAttitude`, `KeyCompassHeading` | `app/flight/dji/DJIAircraft.kt:126-152` |
| RTMP live stream | `MediaDataCenter.liveStreamManager` | `app/flight/dji/DJICamera.kt:22,84` |

Two safety behaviours are worth naming. The virtual-stick loop transmits at 18 Hz
(`app/flight/AircraftController.kt:289-291`). If the RC sticks deviate by more than 30 units, the
app treats it as a manual override. It then cancels the flight job, brakes and emergency-stops
(`app/flight/AircraftController.kt:293,364,376`, handled at `:420-425`).

## Corrections to the ground-station assumptions

1. `/input` is **not** a route on the phone. The phone POSTs `/input` to the ground station
   (`app/voice/GroundStationSpeechResolver.kt:46`).
2. Video is **TCP**, not UDP. The phone listens and the ground station connects
   (`app/api/VideoTcpServer.kt:59,67`).
3. The recogniser is Google `SpeechRecognizer` (`app/voice/SpeechResolversVM.kt:98`). A Vosk class
   exists but nothing calls it.
4. No keepalive message is defined for `/c/ws/sticks`. The `WebSockets` plugin is installed with a
   content converter only (`app/api/server/ApiServer.kt:134-139`). No ping interval and no timeout
   are set.
5. Routes exist that the brief did not list: `GET /`, `POST /key`, `GET /(fly|takeoff)`, `GET /land`,
   `GET /c/(wave|hi|hey|hello)`, `POST /c/stream/start`, `POST /c/stream/stop`,
   `GET /c/stream/status`, `WS /c/ws/gimbal`, `WS /c/ws/telemetry`.
6. `GET /(fly|takeoff)` and `GET /land` bypass `AircraftController` entirely. They fire DJI keys
   directly (`app/api/server/ApiServer.kt:374,382`). Gate A covers them. Gate B does not.

## Not verified

- The runtime behaviour of a `503` on a WebSocket upgrade request. The intercept is registered on
  the routing pipeline (`app/api/server/ApiServer.kt:159`), so it should run before the upgrade.
  Nothing was executed to confirm the wire behaviour.
- Ktor's default WebSocket ping and timeout values. The dependency version was not read.
- `VoskSpeechRecognizer` (`app/voice/VoskSpeechRecognizer.kt:21`) is never referenced anywhere in
  the app. It appears to be dead code. No build variant was checked.
- `LlamaActionSequenceResolver` is constructed (`app/voice/VoiceControlFragment.kt:145`) but its
  registration is commented out (`app/voice/VoiceControlFragment.kt:65-68`). Its `init()` is also
  commented out (`app/voice/VoiceControlFragment.kt:153-163`). The on-phone LLM path is inactive.
- The video codec. `H.264` comes from the ground-station brief, not from the app code. The app only
  logs `info.mimeType` at runtime (`app/api/VideoTcpServer.kt:30`).
- The Hebrew regex literals at `res/values-iw/strings.xml:19-61` were read but are not reproduced
  here. Only the resource names and line numbers are cited.
- `MainActivity` and the navigation graph that reaches the "API Server" screen were not read.
- The Cloudflared tunnel exposes port 8080 publicly on every service start
  (`app/api/server/ApiServerVM.kt:110`). Whether it succeeds in the field was not tested.
- `TTSRequest.rate` (`app/api/dto/TTSRequest.kt:14`) is decoded but not passed to
  `TTSManager.speak`. Read from the code, not executed.
