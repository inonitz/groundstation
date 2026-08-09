# Real Tello bring-up

Hardware launcher for the real DJI Tello. This is the real-flight counterpart to
`scripts/test/` (SITL). No Gazebo, no PX4, no simulation. You run it on the laptop,
standing next to the drone, over the Tello's own WiFi.

## Layout
```
scripts/tello/
  run.sh      # brings up RX (--tello) + FMU (tello backend) + keyboard, in one tmux session
  README.md   # this file
```

## Prerequisites

The host laptop must be joined to the Tello's WiFi AP (SSID `TELLO-XXXXXX`). The host
then gets `192.168.10.2` and the drone is `192.168.10.1`. That IP is hardcoded in
`source/llm_to_action/tello_backend/tello_backend_base.hpp`, so there is no flag to set.

Charge several batteries first. One battery gives about 10-13 minutes of flight, so
bring-up plus a real mission will burn through more than one.

## Build

`build.sh` takes the backend as its third argument, so a Tello-only tree is one command.
It builds only the Tello backend: no PX4 backend, no Gazebo camera plugin, no px4_msgs, no
gz-sim8.

```bash
cd /root/groundstation
./build.sh release shared tello configure
./build.sh release shared tello build
```

Output lands in `build/release/shared/tello/`. This produces
`build/release/shared/tello/bin/llm_to_action_fmu_tello`, plus the shared
`llm_to_action_gstreamer_rx` and `llm_to_action_keyboard_hook`. `run.sh` refuses to start
if any of the three are missing.

## Run

```bash
cd scripts/tello
./run.sh
```

Three panes come up: the video receiver, the FMU, and the keyboard teleop. Click the
keyboard pane to give it focus before you fly. The FMU connects the Tello, enters command
mode, sends `streamon`, and starts the 20Hz control loop. The rc keepalive rides on that
same loop, so the drone keeps getting stick updates without any extra code. The Tello
auto-lands if the keepalive stops for about 15 seconds, so keep the FMU pane alive in
flight.

The VLM is not started by `run.sh`. Bring-up (video decode, telemetry, keepalive) does not
need it. To fly the VLM-driven T1 mission, start `llama-server` in a fourth pane, the same
way `scripts/test/lib/sim_core.sh` does (`CMD_VLM`).

## What success looks like

- The RX pane logs `GStreamer Receiver Node Active (Tello raw-H264 pipeline)`, then a few
  GStreamer state changes, then goes quiet. Quiet means frames are flowing; loud means a
  pipeline error (see below).
- The FMU pane logs the Tello connect and `streamon` ack, then a steady stream of control
  and rc lines. The rc keepalive is holding if those lines keep printing past 15 seconds.
- Telemetry parses without a flood of parse-error lines.

## When it fails

Check the `llm_to_action_gstreamer_rx --tello` pane's own stderr first. A pipeline mistake
shows up there as a GStreamer `Error:` line. Common causes: the host is not on the Tello
WiFi (no UDP reaches 11111), or `streamon` never ran (check the FMU pane for the ack). No
`Error:` and no frames usually means the FMU never sent `streamon` or nothing is arriving
on 11111 -- confirm the WiFi association and that the FMU pane got its `streamon` ok.

## Land and stop

Land with the keyboard before you stop the session. Do not kill the panes mid-flight; the
cleanup path `pkill`s the FMU, which cuts the rc keepalive and drops the drone into its own
~15s auto-land. To re-arm and fly again, land, then take off again from the keyboard. When
the battery runs low, land, swap the battery, and rerun `./run.sh`.
