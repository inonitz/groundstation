#!/usr/bin/env python3
"""The harden2 ground-station app. It builds the SERVICES, gives each MODULE the services
it needs, runs the screen, then closes the modules and the services in reverse order
(owner ruling 2026-09-23). Anything that fails while starting dies with the reason.

  voice "highlight the red backpack" -> SAM3 finds and masks it; the box follows it
  voice "how many people"            -> SAM3 counts them (the median of a few frames)
  voice "what do you see"            -> Gemma answers in the chat pane
  voice "clear"                      -> drop the highlight

  python3 -m app.main --source 0     # from the harden2 root: webcam 0
  python3 -m app.main                # the source from config (VIDEO=webcam|dji)

Global keys (any window): F4 kill toggle | F1 quit | F2 clear highlight | F5 talk.
Window keys: q/Esc quit | c clear highlight | t masks on/off | [ ] or mouse wheel scroll
the chat | x clear chat
"""
import time

# the "startup" perf stage counts from here, the imports included
LAUNCHED = time.monotonic()

import argparse
import os
import subprocess
import sys
from functools import partial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)   # the harden2 root: every module imports from here

# no package check here (owner Q5 a, 3.2.3): `run.sh preflight` (runtime/deps.py) is its
# one place; "If a service crashes then we will run the preflight"
import config
from app.state import S
from app.turns import Turns, VisionSinks, say_with
from app.ui import Ui
from audio import asr_ros
from audio.speech_in import SpeechIn
from audio.speech_out import SpeechOut
from control.flight import Control, outcome_text
from dji_app import client as dji_module
from dji_app.client import DjiApp
from gemma import server as gemma_process
from gemma.client import Gemma
from keys import keys as keys_module
from keys.keys import Keys
from log.perf import Perf
from log.session import SessionLog
from sam3.loader import BackendLoader
from perception2.vision import Vision
from recognizer import Recognizer
from recognizer.recognizer import warm_up as plan_warm_up
from runtime import ros
from runtime.fatal import die, install_crash_hooks
from runtime.status import StatusBoard
from runtime.supervisor import Supervisor
from video import ros_stream
from video.video import Video, source_kind


def parse_source():
    """The one CLI argument: the video source (falls back to config.INPUT)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=config.INPUT)
    return parser.parse_args().source


def start_processes(supervisor, log_dir, source, gemma=None):
    """Start every process a configured option needs. -> (every Process handle, the
    gstreamer handle or None). @gemma: the Gemma client; its server's row turns UP after
    one warm-up plan through it (owner L1). None: no warm-up."""
    warm_up = None
    if gemma is not None:
        warm_up = partial(plan_warm_up, gemma)
    processes = [
        supervisor.start(gemma_process.process(log_dir, warm_up=warm_up)),
        supervisor.start(keys_module.process(log_dir)),       # always: F4 needs it
    ]
    if "ros" in config.ASR_SOURCES:
        processes.append(supervisor.start(asr_ros.process(log_dir)))

    if not config.DJI_REAL:
        processes.append(supervisor.start(dji_module.mock_process(log_dir)))

    if source_kind(source) != "ros":
        return processes, None

    if not config.PHONE_IP:
        die("VIDEO=dji but no phone IP: join the phone hotspot, or export PHONE_IP")
    gstreamer = supervisor.start(ros_stream.process(log_dir, config.PHONE_IP))
    processes.append(gstreamer)
    return processes, gstreamer


class Services:
    """Every service, built by ONE call at start (owner D15: "the app should simply call
    a single function that 'builds' all the services"), in this order: the session log,
    perf, the supervisor, the Gemma client, the processes the settings need (the Gemma
    server is warmed through the client), the phone-app client, the SAM3 loader (it
    warms SAM3 up). Each system gets from here only the services it needs.
    Everything loads now, nothing during the run (owner 3.3). close(): in reverse."""

    def __init__(self, source, imports_ms):
        # the start-up check: an unwritable folder dies
        self.log = SessionLog(config.SESSION_DIR)
        self.perf = Perf(self.log.dir)              # every run's timings: perf.jsonl
        self.perf.record("startup", imports_ms, row="imports")
        self.perf.start_gpu_sampler()
        self.supervisor = Supervisor()      # every process: restart, wait, or die
        # the client before the processes: the Gemma server is warmed through it
        self.gemma = Gemma(perf=self.perf)
        self.processes, self.gstreamer = start_processes(
            self.supervisor,
            self.log.dir,
            source,
            self.gemma
        )
        self.dji = DjiApp.from_env(self.perf)   # the phone app (or the mock)
        self.sam3 = BackendLoader(config.SEG)
        return

    def close(self):
        for service in (self.sam3, self.dji, self.gemma):
            service.close()
        self.supervisor.stop_all()      # every process the app started
        self.perf.close()
        self.log.close()
        return


def main():
    install_crash_hooks()      # an uncaught exception in any thread -> die()
    imports_ms = (time.monotonic() - LAUNCHED) * 1000
    source = parse_source()

    # --- services -----------------------------------------------------------------
    services = Services(source, imports_ms)
    log = services.log
    perf = services.perf
    gemma = services.gemma
    dji = services.dji
    sam3 = services.sam3

    # --- modules ------------------------------------------------------------------
    speech_out = SpeechOut(config.TTS_OUTPUTS, dji, perf=perf)
    say = say_with(speech_out)
    video = Video(source, services.gstreamer)
    control = Control(dji, log)
    sinks = VisionSinks(log, speech_out.say)
    vision = Vision(
        sam3,
        gemma,
        video.snapshot,
        sinks.sinks(),
        use_masks=use_masks,
        perf=perf
    )
    recognizer = Recognizer(control, vision, gemma, log)
    turns = Turns(recognizer, say, log, perf=perf)
    speech_in = SpeechIn(config.ASR_SOURCES, turns)

    # the status pane asks each part for its own rows, in this order
    board = StatusBoard([*services.processes, dji, sam3, video, speech_in])
    perf.watch_startup(board.snapshot, LAUNCHED)
    ui = Ui(video, board, log.dir, control.manual_on, perf=perf)
    keys = Keys(
        partial(
            on_global_key,
            control=control,
            say=say,
            quit_app=ui.request_quit,
            clear=vision.clear
        ),
        on_release=partial(on_key_release, perf=perf)
    )

    # --- run: a crash in the display loop reaches the crash hook -> die ------------
    ui.run(on_clear=vision.clear)

    # --- shutdown: the modules, then the services, each in reverse order ------------
    for module in (keys, ui, speech_in, recognizer, vision, control, video, speech_out):
        module.close()
    ros.stop()                 # after the last ROS2 node
    services.close()

    # launched by run.sh: quit tears the whole tmux session down
    if config.TMUX_SESSION:
        subprocess.run(["tmux", "kill-session", "-t", config.TMUX_SESSION], check=False)
    # bypass the torch/ROCm interpreter-teardown crash: exit 0, no core dump
    os._exit(0)


def on_key_release(code, perf):
    """The push-to-talk release starts the ASR and e2e timings (Turns reads it on the
    text)."""
    if code != config.PUSH_TO_TALK_KEY_CODE:
        return
    perf.mark("ptt_release")
    return


def on_global_key(code, control, say, quit_app, clear):
    """A global key press, from any window. Only function keys act (owner 2026-09-23:
    letters are typed in other windows): the kill key toggles manual mode and says the
    result, the quit key quits the app, the clear key drops the highlight."""
    if code == config.QUIT_KEY_CODE:
        quit_app()
        return
    if code == config.CLEAR_KEY_CODE:
        clear()
        return
    if code != config.KILL_KEY_CODE:
        return

    action, status = control.toggle_manual()
    say(outcome_text(action, status))
    return


def use_masks():
    with S.lock:
        return S.use_sam


if __name__ == "__main__":
    main()
