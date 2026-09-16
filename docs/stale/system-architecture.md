# Groundstation — System Architecture

**VLM plans, deterministic math flies.** Off-board drone control for two targets from one codebase:
PX4/Gazebo in simulation and a physical DJI Tello. A vision-language model turns an objective and a
live camera into a verb plan; a 20 Hz control loop executes it against whichever flight backend is
attached.

This is drawn as the **target system with voice control assumed complete**. Open it in the VS Code
Markdown preview (or any mermaid renderer) to see the diagrams. FMU / FOLLOW facts are verified against
source by the FOLLOW session; the localization plane is reconciled with the SLAM session (no dead-reckoning; SLAM-or-land).

- **FMU node:** `high_level_navigation_node`
- **VLM:** Qwen3-VL-2B via `llama-server`
- **ASR:** Parakeet-q4 (push-to-talk)
- **Verbs:** takeoff · land · go · rotate · orbit · search · approach · follow · hover · stop · re-assess

**Colour key** (as rendered by the `classDef` fills): grey/slate = **shared** (both targets),
blue = **SITL-only** (PX4 / Gazebo), green = **Tello-only** (physical), amber dashed = **proposed —
new this push (ASR)**.

---

## 1. System dataflow

Every process and the transport between them. One camera source feeds perception and SLAM; the FMU
plans against the VLM over HTTP and drives a flight backend. The one substitution between targets is
the camera source and the backend output — everything in the middle is shared.

```mermaid
flowchart TB
  classDef shared fill:#e8eef5,stroke:#33475b,color:#17212e,stroke-width:1.2px;
  classDef sitl   fill:#dce9f7,stroke:#2f6fb0,color:#123,stroke-width:1.2px;
  classDef tello  fill:#dbeee7,stroke:#22836a,color:#0c2b23,stroke-width:1.2px;
  classDef prop   fill:#fbeecb,stroke:#b9791a,color:#5a3d0a,stroke-width:1.4px,stroke-dasharray:5 3;

  GZ["Gazebo · gz_x500_gimbal<br/>(SITL)"]:::sitl
  TL["DJI Tello<br/>wifi 192.168.10.1"]:::tello
  RX["gstreamer rx node<br/>UDP H.264 :11111"]:::shared
  FMU["<b>high_level_navigation_node</b><br/>perception · planning · 20Hz control"]:::shared
  VLM["llama-server<br/>Qwen3-VL-2B · HTTP :8080"]:::shared
  SLAM["stella_vslam<br/>monocular"]:::tello
  KB["keyboard_hook"]:::shared
  ASR["asr_node · Parakeet-q4<br/>push-to-talk"]:::prop
  DASH["dashboard serve.py<br/>MJPEG + SSE"]:::shared
  PX4["PX4 SITL<br/>(EKF2)"]:::sitl

  GZ -->|H.264 UDP| RX
  TL -->|H.264 UDP :11111| RX
  RX -->|camera frames<br/>UDPCamMsgType| FMU
  RX -->|camera frames| SLAM
  FMU <-->|HTTP POST /v1/chat/completions<br/>plan · GBNF grammar| VLM
  KB -->|/fmu/in/override Bool<br/>/keyboard/in/raw| FMU
  ASR -.->|/asr_server/transcribe<br/>writes m_initialCommand| FMU
  SLAM -.->|standalone hover loop → TelloBackend<br/>(FMU wiring deferred)| TL
  FMU -->|set_velocity<br/>ENU→NED setpoint stream| PX4
  FMU -->|set_velocity<br/>ENU→body-FLU rc a b c d| TL
  FMU -->|/fmu/perception/annotated · depth<br/>/fmu/hud · vlm_text · vlm_context · rates<br/>obs-gated| DASH
```

**The spine.** The FMU is the hub: it fuses perception, calls the VLM for a plan, and streams velocity
to the backend. `set_velocity` is the common seam — PX4 gets NED trajectory setpoints, the Tello gets
body-frame `rc`. The amber dashed edge is the only genuinely new wiring: ASR does not reach the FMU yet.

> **ASR seam — proposed, not built.** Today an objective enters only at startup
> (`start(objective) → m_initialCommand`, from argv / `FMU_OBJECTIVE`). There is no runtime path to
> change it. Voice control adds one subscription to `/asr_server/transcribe` that writes
> `m_initialCommand` and re-triggers `maybePlan()`. That single edge is the whole integration.

---

## 2. Localization — where the two targets diverge

The only deep split. In simulation PX4's EKF2 hands the FMU a closed **absolute** position. On the Tello
there is **no absolute XY from hardware** — the sole source is monocular SLAM off the **forward** camera,
and only while that scene stays textured. There is **no dead-reckoning**: the Tello's `vgx/vgy` are
VPS-derived and read a false zero exactly when the VPS goes blind, so integrating them would report real
drift as stillness. That path was tried and dropped.

```mermaid
flowchart TB
  classDef shared fill:#e8eef5,stroke:#33475b,color:#17212e,stroke-width:1.2px;
  classDef sitl   fill:#dce9f7,stroke:#2f6fb0,color:#123,stroke-width:1.2px;
  classDef tello  fill:#dbeee7,stroke:#22836a,color:#0c2b23,stroke-width:1.2px;
  classDef na     fill:#ededed,stroke:#9aa6b2,color:#6b7684,stroke-width:1px,stroke-dasharray:3 3;

  subgraph S["SITL — position is free"]
    direction TB
    EKF["PX4 EKF2"]:::sitl -->|/fmu/out/vehicle_odometry| ODOM_S["odometry()<br/>absolute position"]:::sitl
  end
  ODOM_S --> FMU["FMU control loop"]:::shared

  subgraph T["Tello — standalone hover loop, NOT via the FMU"]
    direction TB
    STE["stella SLAM · forward cam<br/>slam/pose (up-to-scale) · ~27 Hz"]:::tello
    STE -->|axis remap → map→ENU align (yaw0 pinned)<br/>→ scale-from-height: tof / -y, running median| PID["hover-hold PID<br/>tello_slam_hold"]:::tello
    PID -->|set_body_velocity (FLU)| TBK["TelloBackend"]:::tello
    STE -->|slam/tracking_state Bool<br/>+ pose-freshness| FSM{"recovery FSM<br/>TRACK → LOST_HOLD ~2s → LAND"}:::tello
    FSM -->|still lost → vertical-only land (tof/baro)| TBK
    DR["dead-reckoning / fusion<br/>DROPPED — vgx/vgy false-zero when blind"]:::na
  end
```

**SITL is one arrow; the Tello is a standalone loop the FMU does not yet see.** On SITL, EKF2 gives the
FMU real position and the FOLLOW headline runs on it. On the Tello, `tello_slam_hold` is its own
executable — SLAM → scale-by-height → PID → TelloBackend — with no wiring into the FMU yet. Lose
tracking and the FSM holds for ~2 s, then lands vertically on tof/baro; it never traverses blind.

> **Two surfaces, both required.** stella needs the **forward** scene textured (forward camera); the
> onboard VPS needs the **floor** textured (downward camera). Glass or smooth concrete blinds either, so
> flying the Tello at all is preconditioned on a continuously textured forward scene. Status: stella
> bring-up landed (~27 Hz on the real drone); the hover-hold node is built and in hardware bring-up; the
> recovery FSM is offline-tested, hardware-unconfirmed; dead-reckoning is dropped.

## 3. Voice → plan → flight

The runtime sequence a spoken objective moves through, end to end. The proposed ASR steps are shaded;
everything from the VLM call onward exists today.

```mermaid
sequenceDiagram
  autonumber
  actor OP as Operator
  participant ASR as asr_node (Parakeet)
  participant FMU as FMU (nav node)
  participant VLM as llama-server (VLM)
  participant BE as Flight backend
  participant DR as Drone

  rect rgb(251,238,203)
  OP->>ASR: push-to-talk + speak objective
  ASR->>ASR: capture · resample · transcribe (raw audio)
  ASR-->>FMU: /asr_server/transcribe  [PROPOSED]
  FMU-->>OP: echo "[ASR] heard: …"  (read-back)
  OP->>FMU: confirm
  FMU->>FMU: write m_initialCommand · maybePlan()
  end

  loop event-driven planning wake
    FMU->>VLM: POST /v1/chat/completions<br/>[PERCEPTION] + state + history · GBNF
    VLM-->>FMU: plan = [thought, verbs…]
  end
  FMU->>FMU: translateToBaseCommands() → queue
  loop 20 Hz control loop
    FMU->>BE: set_velocity (per-verb servo)
    BE->>DR: trajectory_setpoint (PX4) / rc (Tello)
    DR-->>FMU: odometry (EKF2 on SITL; Tello XY not fed to FMU)
  end
  Note over FMU,DR: FOLLOW — resolve once (VLM track_id → index → centre),<br/>per-tick label + nearest-centroid, yaw+vertical centre,<br/>forward clamped ≤ 0, loss = HOLD + re-acquire
```

**Confidence is not in this picture on purpose.** The ASR confidence score was tested and does not
track correctness, so the safety net is operator read-back (steps 4–5), not an automatic gate. From the
VLM call down, this is the live control path.

---

_Target system · ASR assumed complete · 2026-08-12. A styled standalone HTML version lives in the
session scratchpad (`groundstation-system.html`) for rendering as a shareable page once artifact
publishing is available._
