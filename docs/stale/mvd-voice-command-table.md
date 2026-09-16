# MVD Voice Command Table — Laptop/Phone ASR → DjiWire → DJI Backend POST

Definitive, current reference. Same pipeline for laptop mic (press H) and phone ASR (`POST :8080/input`).
Source of truth: `projects/integration/commands.py` (patterns) + `router.py` (dispatch) + `dji_wire.py`.
Full context: `docs/active/2026-08-25-mvd-integration-handoff.md`.

## Tiers (checked first, length-INDEPENDENT)

| Say (any of) | Router → DjiWire | DJI Backend POST |
|---|---|---|
| stop · halt · abort · freeze · kill · cut · emergency · mayday | `halt()` | `POST /c/fly [{"type":"delay","seconds":0}]` |
| manual · override · take over · i have control · my control · disengage | `stop()` + mode→manual | `POST /c/stop` |
| resume · auto · autonomous · you have control · take control | mode→auto | *none (our state)* |

## BASIC verbs (only if ≤ 4 words)

| Say | Router → DjiWire | DJI Backend POST |
|---|---|---|
| takeoff · take off · fly · liftoff · sky · wakeup | `takeoff()` | `POST /c/takeoff` |
| land · landing · perch · floor · ground | `land()` | `POST /c/land` |
| spin · spin around | `spin_by(360)` | `POST /c/fly [{spin_by, degrees:360}]` |
| scan | `scan_ground(OUTWARDS)` | `POST /c/fly [{scan_ground, facing:"OUTWARDS"}]` |
| search · recon | `scan_ground(INWARDS)` | `POST /c/fly [{scan_ground, facing:"INWARDS"}]` |
| forward · forwards · go forward | `fly_by(dx:+1)` | `POST /c/fly [{fly_by, dx:1.0, velocity:2.0}]` |
| back · backward · backwards · back up | `fly_by(dx:-1)` | `POST /c/fly [{fly_by, dx:-1.0, velocity:2.0}]` |
| right · rightward(s) | `fly_by(dy:+1)` | `POST /c/fly [{fly_by, dy:1.0, velocity:2.0}]` |
| left · leftward(s) | `fly_by(dy:-1)` | `POST /c/fly [{fly_by, dy:-1.0, velocity:2.0}]` |
| up · rise · high | `fly_by(dz:+1)` | `POST /c/fly [{fly_by, dz:1.0, velocity:2.0}]` |
| down · under · low | `fly_by(dz:-1)` | `POST /c/fly [{fly_by, dz:-1.0, velocity:2.0}]` |
| look / watch / track (at) me / us | `track_me()` | `POST /c/fly [{track_me}]` |
| follow · follow me · follow him | `follow_me()` | `POST /c/fly [{follow_me}]` |
| come back · come home · return home · go home | `go_home_to_user()` | `POST /c/fly [{home}]` |
| look/camera/face forward · ahead · straight | `gimbal_pitch(0)` | `POST /c/fly [{gimbal_pitch, angle:0}]` |
| look/camera/gimbal down | `gimbal_pitch(-60)` | `POST /c/fly [{gimbal_pitch, angle:-60}]` |
| look/camera/gimbal up | `gimbal_pitch(30)` | `POST /c/fly [{gimbal_pitch, angle:30}]` |
| hello · hey · hi · heya · hiya · wave · how are you · how's it going | `wave()` | `POST /c/fly [{wave}]` |
| go / move / head + **no valid direction** | `unknown_move` | *no-op + "didn't catch a direction" (never scene-describe)* |

## COMPLEX (anything else, or > 4 words)

→ **perception** (Qwen-VL + OmDet/SAM2 on the laptop). **No drone POST.**
Answer is split: **LONG → screen (`Scene:`)** and **SHORT → phone `/tts` + laptop espeak + screen (`Spoken:`)**.
Examples: "what do you see", "how many windows", "highlight the red backpack", "show me all the windows".

## Notes
- Length guard: BASIC verbs only fire on ≤ 4 words (`MVD_MAX_CMD_WORDS`). Tiers ignore length.
- Tunables (router): `move_m=1.0` m, `move_vel=2.0` m/s, `spin_deg=360`.
- `stop` = `delay:0` preempts current motion AND keeps our stick control (`controller.fly` re-`takeControl`s);
  it is NOT `/c/stop`, and it no longer latches manual.
- Indoors only yaw/gimbal/vertical/spin/wave/takeoff/land are reliable; `fly_by`/`scan`/`track`/`follow`/
  `come_home` need GPS/VPS (outdoor). Gimbal is currently broken BACKEND-side (`fly_by` works).
- Every dispatch logs `[dji] POST <path> {body} -> HTTP <code>` in the app pane / `/tmp/mvd_app.log`.

## Exact wire JSON (the `[{...}]` shorthand above expands to this)
`POST /c/fly` body is a mission array with a `type` discriminator per action:
```
POST /c/fly    {"mission": [ {"type": "<name>", ...fields} ]}
```
So the shorthand maps to the literal payloads:
- spin        → `{"mission":[{"type":"spin_by","degrees":360.0}]}`
- scan        → `{"mission":[{"type":"scan_ground","radius":3.0,"velocity":4.0,"facing":"OUTWARDS","clockwise":true}]}`
- search      → `{"mission":[{"type":"scan_ground","radius":3.0,"velocity":4.0,"facing":"INWARDS","clockwise":true}]}`
- forward     → `{"mission":[{"type":"fly_by","dx":1.0,"dy":0.0,"dz":0.0,"velocity":2.0}]}`  (dx/dy/dz per direction)
- track       → `{"mission":[{"type":"track_me","fovTolerance":17.0}]}`
- follow      → `{"mission":[{"type":"follow_me","cruiseHeight":7.0,"followDistance":3.5,"maxVelocity":8.0}]}`
- come home   → `{"mission":[{"type":"home","maxVelocity":4.0}]}`
- gimbal      → `{"mission":[{"type":"gimbal_pitch","angle":-60.0}]}`  (0 / -60 / 30)
- wave        → `{"mission":[{"type":"wave","count":2}]}`
- stop        → `{"mission":[{"type":"delay","seconds":0.0}]}`
Discrete (not `/c/fly`): takeoff → `POST /c/takeoff` (empty body); land → `POST /c/land`; manual → `POST /c/stop`.
Content-Type: application/json. Enum values (`facing`, etc.) serialize by NAME.
