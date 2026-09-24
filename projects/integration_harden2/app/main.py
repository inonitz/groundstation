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

Keys: F4 kill toggle (global, any window) | q/Esc quit | c clear highlight | t masks
on/off | [ ] or mouse wheel scroll the chat | x clear chat
"""
import argparse
import os
import subprocess
import sys
from functools import partial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)   # the harden2 root: every module imports from here

import config
from app import keys as keys_module
from app.keys import Keys
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
from log.session import SessionLog
from perception2.backend import BackendLoader
from perception2.vision import Vision
from recognizer import Recognizer
from system import ros
from system.fatal import die, install_crash_hooks
from system.status import StatusBoard
from system.supervisor import Supervisor
from video import ros_stream
from video.video import Video, source_kind


def parse_source():
    """The one CLI argument: the video source (falls back to config.INPUT)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=config.INPUT)
    return parser.parse_args().source


def start_processes(supervisor, log_dir, source):
    """Start every process a configured option needs. -> (every Process handle, the
    gstreamer handle or None)."""
    processes = [
        supervisor.start(gemma_process.process(log_dir)),
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


def main():
    install_crash_hooks()      # an uncaught exception in any thread -> die()
    source = parse_source()

    # --- services -----------------------------------------------------------------
    log = SessionLog(config.SESSION_DIR)   # the start-up check: unwritable -> die
    supervisor = Supervisor()              # every process: restart, wait, or die
    processes, gstreamer = start_processes(supervisor, log.dir, source)
    gemma = Gemma()
    dji = DjiApp.from_env()    # the phone app (or the mock): commands AND /tts
    sam3 = BackendLoader(config.SEG)

    # --- modules ------------------------------------------------------------------
    speech_out = SpeechOut(config.TTS_OUTPUTS, dji)
    say = say_with(speech_out)
    video = Video(source, gstreamer)
    control = Control(dji, log)
    sinks = VisionSinks(log, speech_out.say)
    vision = Vision(sam3, gemma, video.snapshot, sinks.sinks(), use_masks=use_masks)
    recognizer = Recognizer(control, vision, gemma, log)
    turns = Turns(recognizer, say, log)
    speech_in = SpeechIn(config.ASR_SOURCES, turns)
    keys = Keys(partial(on_global_key, control=control, say=say))

    # the status pane asks each part for its own rows, in this order
    board = StatusBoard([*processes, dji, sam3, video, speech_in])
    ui = Ui(video, board, log.dir, control.manual_on)

    # --- run: a crash in the display loop reaches the crash hook -> die ------------
    ui.run(on_clear=vision.clear)

    # --- shutdown: the modules, then the services, each in reverse order ------------
    for module in (ui, keys, speech_in, recognizer, vision, control, video, speech_out):
        module.close()
    ros.stop()                 # after the last ROS2 node
    for service in (sam3, dji, gemma):
        service.close()
    supervisor.stop_all()      # every process the app started
    log.close()

    # launched by run.sh: quit tears the whole tmux session down
    if config.TMUX_SESSION:
        subprocess.run(["tmux", "kill-session", "-t", config.TMUX_SESSION], check=False)
    # bypass the torch/ROCm interpreter-teardown crash: exit 0, no core dump
    os._exit(0)


def on_global_key(code, control, say):
    """A global key press. Only the kill key acts: it toggles manual mode and says the
    result. Letters never act: they are typed in other windows (owner 2026-09-23)."""
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
