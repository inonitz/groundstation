# integration_harden2 — the single-model Hebrew voice-drone stack (architecture, 2026-09-08)

One GPU model does the language work: Gemma 4 E4B reads the Hebrew, routes it, plans the mission, names the
object for the segmenter, looks at the frame, and answers in Hebrew. whisper does the ears, SAM3 does the eyes.
Solid boxes exist and ran live on 2026-09-08 (webcam + mock). Dashed boxes are not built.

**This is the LIVE system's architecture** (the repo's primary one). The frozen fallback is `integration_tts`; the parked C++ destination engine is `spec-fmu-architecture.md`.

## Simplified, demo-day style (same three lanes as the 2026-08 diagram)

```mermaid
flowchart LR
    PILOT(["Pilot, Hebrew voice"])
    subgraph MOBILE["Mobile Device (phone, hotspot to the ground station)"]
        GSR["Google SpeechRecognizer"]
        PRX{"phone Regex: basic and critical commands"}
        API["REST API Web Server<br/>/c/takeoff /c/fly /c/land /c/stop, /tts, /input<br/>WebSocket /c/ws/sticks: virtual sticks + keepalive"]
        SPK(("speaker"))
    end
    RC["DJI Remote Controller"]
    DRONE(("DJI drone"))
    subgraph GS["Ground Station (laptop, everything local)"]
        ASR["ASR: whisper.cpp Hebrew, F5"]
        RX{"Regex: emergency stop, basic verbs"}
        subgraph GEMMA["Gemma 4 E4B (was: Qwen + DictaLM)"]
            PLAN["Routing + Flight Planning<br/>kind, target, mission"]
            GATE["Presence Gate on the frame"]
            QA["Scene Q and A in Hebrew"]
        end
        NG{"Number Guard"}
        SAM["SAM3: Highlighting + Counting"]
        KILL["Kill Switch, M key"]
        GST["gstreamer node in ROS2<br/>H.264 in from any platform"]
        CAM["CameraStream + overlay"]
    end
    PILOT -->|"voice"| GSR --> PRX
    PRX -->|"caught"| API
    PRX -->|"not caught: text"| RX
    PILOT -->|"voice"| ASR --> RX
    RX -->|"stop, simple move"| API
    RX -->|"complex"| PLAN
    PLAN -->|"mission"| NG --> API
    PLAN -->|"highlight, count: target"| GATE --> SAM
    PLAN -->|"question"| QA -->|"short Hebrew answer via /tts"| API --> SPK
    KILL -->|"/c/stop"| API
    API <--> RC <--> DRONE
    DRONE -.->|"video"| RC -.-> API -.->|"H.264 packets"| GST --> CAM
    CAM --> GATE
    CAM --> SAM
    CAM --> QA
```

Changes against the demo-day system, one per line:
- ASR: the phone's Google SpeechRecognizer stays as the first line: a regex on the phone handles basic and critical commands; what it does not catch comes to the ground station as text (/input). The laptop path is whisper.cpp Hebrew.
- Qwen -> Gemma 4. One model does routing, flight planning, the presence gate and the Hebrew scene answers.
- Scene Transcribing + Text Simplifier -> one box, Scene Q&A in Hebrew. No translation to English and back any more.
- Highlighting: OmDet + SAM2 -> SAM3, fed by the English target phrase the planner writes.
- New: Number Guard between the plan and the wire. New: Kill Switch on the M key, straight to /c/stop.
- The Regex stays as tier 0 (emergency words, basic verbs). Every command reaches the aircraft through the phone's REST API server, then the DJI Remote Controller; the same server speaks the TTS and forwards the H.264 video, which the gstreamer node in ROS2 turns into our frame source for any platform. The WebSocket /c/ws/sticks is the virtual-stick channel with its keepalive.
- Not in the picture because not built: target approach, SAM3 counting.

To put it into draw.io: Arrange -> Insert -> Advanced -> Mermaid, paste the block above.

## In depth, slide 3: the language path

```mermaid
flowchart LR
    T["Hebrew text"] --> S0{"emergency word"}
    S0 -->|"yes"| STOP["halt on the wire"]
    S0 -->|"no"| S1{"exact simple command"}
    S1 -->|"yes"| BY["deterministic mission, no model"]
    S1 -->|"no"| S2["Hebrew rewrites:<br/>number words, idioms, register"]
    S2 --> G["Gemma 4, one call, grammar-constrained<br/>kind + target phrase + mission"]
    G -->|"mission"| NG{"every spoken number<br/>in the mission"}
    NG -->|"yes"| EC{"copies a prompt example"}
    EC -->|"no"| W["REST /c/fly"]
    NG -->|"no"| RB["Hebrew read-back, nothing flies"]
    EC -->|"yes"| RB
    G -->|"reject"| RB
    G -->|"highlight, count, describe"| P["perception path"]
```

## In depth, slide 4: the perception path

```mermaid
flowchart LR
    P["target phrase in English, from the planner"] --> K{"kind"}
    K -->|"highlight"| GATE["Presence gate: Gemma looks at one frame"]
    GATE -->|"present"| C["head object + its attributes<br/>(relations dropped)"]
    C --> S3["SAM3 nf4: boxes + masks<br/>one forward per second"]
    S3 --> HL["masks on the overlay<br/>dropped after 8 s without a hit"]
    GATE -->|"absent"| NO["I do not see it"]
    K -->|"count"| S3C["SAM3 alone, score 0.5"]
    S3C --> N["number spoken in Hebrew,<br/>objects highlighted"]
    K -->|"describe"| QA["Gemma answers in Hebrew<br/>format grammar"]
    QA --> TTS["phone /tts"]
```

Slide sources (2026-09-09 01:30): graphviz DOT files `docs/active/assets/harden2-{simplified,language,perception,detailed}.dot`, rendered locally with `dot -Tpng` / `dot -Tsvg` at dpi 192 (the llm_to_action lane's recipe: styled nodes, semantic fills, rank rows, aspect near 1.7:1). The mermaid blocks in this document are the in-doc previews of the same content. The webcam desk path (`VIDEO=webcam WEBCAM_DEV=2`) is a test input only and is left out of every diagram on purpose.

## Detailed (every component, with the measured numbers below)

```mermaid
flowchart TB
    subgraph L2A["Reused llm_to_action ROS2 nodes (C++, unchanged)"]
        KEYS["keyboard_hook<br/>F5 push-to-talk -> /keyboard/in/raw"]
        ASRN["asr_server<br/>whisper.cpp ivrit large-v3-turbo q5_k<br/>-> /asr_server/transcribe"]
        GST["gstreamer_rx<br/>H.264 :5600 -> camera/stream"]
    end
    subgraph PHONE["Phone (hotspot)"]
        PSR["Google SpeechRecognizer + phone regex"]
        API["REST API server :8080<br/>/c/fly /c/takeoff /c/land /c/stop, /tts, /input<br/>WebSocket /c/ws/sticks"]
        SPK(("speaker"))
    end
    RC["DJI Remote Controller"] <--> DRONE(("DJI drone"))
    API <--> RC
    subgraph APP["mvd.py, the ground-station app"]
        EARS["Ears: ROS2 subscriber to /asr_server/transcribe<br/>phone_ears: POST /input from the phone"]
        TH["TextHandler"]
        ROUTER["Router (control/): tier 0 emergency regex, basic verbs"]
        DIRECT["recognize_direct: emergency, bypass, Hebrew rewrites"]
        GUARD["number guard + few-shot echo guard"]
        WIRE["DjiWire: POST /c/fly, /c/stop"]
        KILL["KillSwitch, M key: /c/stop + latch"]
        GATE["presence gate: one frame to Gemma, format grammar"]
        SAM["SAM3-nf4 (perception2)<br/>highlight 1 forward/s, count at 0.5, 8 s give-up"]
        CS["CameraStream: camera/stream"]
        HUD["overlay HUD: masks, chat, fps, kill state"]
        REC["session recorder: utterances.jsonl + clips"]
    end
    GEMMA["Gemma 4 E4B, llama-server :18090, thinking off<br/>UNIFIED_GRAMMAR: kind, target_en, mission<br/>VLM answers in Hebrew"]
    MIC(["microphone"]) --> ASRN
    KEYS -->|"record on/off"| ASRN
    ASRN --> EARS
    PSR -->|"not caught"| API -->|"/input"| EARS
    EARS --> TH --> ROUTER
    ROUTER -->|"stop, simple move"| WIRE
    ROUTER -->|"complex"| DIRECT --> GEMMA
    GEMMA -->|"mission"| GUARD --> WIRE --> API
    KILL --> WIRE
    GEMMA -->|"highlight, count: target_en"| GATE --> SAM --> HUD
    GEMMA -->|"describe: Hebrew answer"| API --> SPK
    DRONE -.->|"video"| RC -.-> API -.->|"H.264"| GST --> CS
    CS --> HUD
    CS --> GATE
    CS --> SAM
    TH -.-> REC
```

## What each box is measured at (2026-09-08)

| box | number | source |
|---|---|---|
| whisper q5_k | CER 8.4 % on 107 live clips; 0.29 s per clip | tools/bench/hebrew_asr/README.md |
| Gemma unified call, 488 bench | 415/466 without the military set (harden: 410) | tools/bench/hebrew-command-bench/results/2026-09-08-unified-gemma4.md |
| Gemma as planner alone, commands | 318/328, thinking off | results/2026-09-08-recognizer-gemma4-direct-nothink.json |
| Gemma gate + SAM3 highlight chain | 28/42 present objects hit (Qwen: 22/42) | tools/bench/whole-system/results/2026-09-08/vision-sam3-chain.md |
| Gemma counting | 2/26 exact | vlm-compare.md |
| Gemma as ASR | CER 35.8 % -> rejected, whisper stays | hebrew_asr/README.md |
| live end to end, webcam + mock | 42 PASS / 17 FAIL of 62 utterances | integration_harden2/sessions/…170015-rog/REPORT.md |
| VRAM, whole stack resident | ~6.5 GiB peak of 8.15 (owner-observed) | live session |

## Switches
MVD_PLANNER=gemma4|qwen3vl · MVD_TRANSLATOR=none|hymt2|dicta · SCENE_SEG=sam3|omdet · SCENE_BG=off|<yolo.pt> ·
VIDEO=webcam|dji|rtmp · WEBCAM_DEV=<n> · SCENE_TTS=phone|off · SCENE_TTS_LANG=he · SCENE_SAM3_PERIOD · SCENE_HL_GIVEUP.
Boot: `MVD_HOME=integration_harden2 VIDEO=webcam WEBCAM_DEV=2 SCENE_TTS=off bash tools/desk-test/up.sh`.

## integration_tts — the frozen fallback

`integration_tts` is the proven English MVD kept as the demo safety net; changes never land there.
Its stack is the pre-harden2 one: English ASR -> a 4-tier deterministic router -> {simple verbs -> DJI
REST | complex queries -> OmDet-Turbo + SAM2 + Qwen-VL perception}, with phone-side Android TextToSpeech
for voice-out. It shares the DJI wire (spec-dji-*) and the ground-station-as-brain model with harden2;
it differs by using the older multi-model perception stack and English instead of the single Gemma-4
Hebrew planner. Full detail: `projects/integration_tts/README.md`.
