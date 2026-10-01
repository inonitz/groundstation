"""Every third-party package, native program and model file the app needs, checked ONCE
at start-up, before any module imports a package (owner ruling 2026-09-23: one file
replaces the scattered find_spec guards). A camera is not checked here: video opens it.

find_spec looks a package up without importing it: it cannot throw, and it does not
load torch + CUDA (5-10 s). Every package is REQUIRED: the install script installs them
all, so no module carries an optional path. A missing package dies with the command
that installs it; a missing file dies with its path.

  python3 -m runtime.deps     # the same check, run by `run.sh preflight`
"""
import importlib.util
import os

import config
from runtime.fatal import die

INSTALL_SCRIPT = "bash /root/groundstation/tools/devenv/install-runtime-deps.sh"
ROS = "source /opt/ros/jazzy/setup.bash"

# import name -> the command that installs it
PACKAGES = {
    "numpy": "pip install numpy",
    "cv2": "pip install opencv-python",
    "PIL": "pip install pillow",
    "bidi": INSTALL_SCRIPT,
    "rclpy": ROS,
    "std_msgs": ROS,
    "sensor_msgs": ROS,
    "torch": "pip install torch",
    "transformers": "pip install transformers",
    "bitsandbytes": INSTALL_SCRIPT,
    "accelerate": INSTALL_SCRIPT,
    "phonikud": INSTALL_SCRIPT,
    "phonikud_onnx": INSTALL_SCRIPT,
    "phonikud_tts": INSTALL_SCRIPT,
    "sounddevice": INSTALL_SCRIPT,
    "pynvml": INSTALL_SCRIPT,
}

# every file the app runs or opens
FILES = [
    config.LLAMA_SERVER_BIN,
    config.ASR_SERVER_BIN,
    config.KEYBOARD_HOOK_BIN,
    config.GSTREAMER_RX_BIN,
    config.GEMMA_MODEL_PATH,
    config.GEMMA_MMPROJ_PATH,
    config.ASR_MODEL_PATH,
    config.SAM3_MODEL_DIR,
    config.SAM3_NF4_DIR,
    config.PHONIKUD_G2P,
    config.PHONIKUD_VOICE,
    config.PHONIKUD_CONFIG,
]


def missing(packages=PACKAGES):
    """-> {import name: install command} for every package that is not installed."""
    absent = {}
    for name, install in packages.items():
        if importlib.util.find_spec(name) is not None:
            continue
        absent[name] = install
    return absent


def missing_files(files=FILES):
    """-> every path in files that does not exist."""
    return [path for path in files if not os.path.exists(path)]


def check(packages=PACKAGES, files=FILES):
    """Die with every missing package (and its install command) and every missing
    file."""
    absent = missing(packages)
    absent_files = missing_files(files)
    if not absent and not absent_files:
        return

    reasons = []
    if absent:
        commands = sorted(set(absent.values()))
        reasons.append(
            f"missing python packages: {', '.join(absent)}. "
            f"Install: {' ; '.join(commands)}"
        )
    if absent_files:
        reasons.append(
            f"missing files: {', '.join(absent_files)} "
            f"(programs: rebuild; models: {INSTALL_SCRIPT})"
        )
    die(" | ".join(reasons))


def main():
    check()
    print(
        f"all {len(PACKAGES)} python packages and {len(FILES)} files present",
        flush=True
    )
    return


if __name__ == "__main__":
    main()
