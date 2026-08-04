[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![MIT][license-shield]][license-url]

<!-- PROJECT LOGO -->
<div align="center">
<h3 align="center">Groundstation</h3>
  <p align="center">
    Off-Board Drone Control and Speech-to-Action Pipeline
  </p>
</div>

## About The Project

Groundstation is a C++ and ROS2 based control system designed to provide almost fully autonomous navigation and control for DJI Tello drones. The core architectural principle of this project is off-board compute: the drone acts strictly as a peripheral, transmitting H.264 video and telemetry over a local network. All intensive processing, including Automatic Speech Recognition (ASR) inference, computer vision, and flight trajectory calculations, executes on the groundstation computer with high performance.

The primary capability demonstrated in the current iteration is a "Speech-To-Action" pipeline. The groundstation captures local microphone audio, processes it through local state-of-the-art AI models (such as Whisper/Sherpa), and translates the transcribed intent into explicit flight control commands. 

Additionally, the project integrates PX4 software-in-the-loop (SITL). PX4 is used strictly for simulation purposes in Gazebo, allowing the system's logic and commands to be safely tested and validated in a virtual environment before deployment to physical hardware.

<br></br>

### Project Structure

The project is structured around ROS2 nodes that communicate via standard topics:

* `source/speech_to_action/`: Contains the core logic for the working demo. Includes the `offboard_node`, which is responsible for taking parsed ASR commands (such as arming states and velocity twists) and converting them into PX4 compatible setpoints for simulation and eventual translation to real drone commands.
* `source/llm_to_action/asr/`: Contains the ASR server node. It manages asynchronous audio capture via a local audio driver and performs speech-to-text inference.
* `source/llm_to_action/keyboard/`: Contains the keyboard hook node utilizing X11. It serves as a push-to-talk trigger (listening for the 'H' key) for the ASR server, and handles W/A/S/D/Arrow inputs for manual override.
* `source/slam/`: Contains work-in-progress implementations for monocular VSLAM (Stella-VSLAM) and OctoMap integration. This module will eventually enable dynamic, GPS-denied localization and autonomous obstacle avoidance.
* `scripts/` & `cmake/`: Build utilities, CMake configurations, and dependency management files (using CPM).

<br></br>

## Getting Started

### Prerequisites

* ROS2 (Humble recommended)
* CMake 3.16 or higher
* A working C++17 compiler toolchain (e.g., Clang or GCC)
* Core Dependencies: Eigen3, OpenCV, GStreamer, X11 (if building in a WSL environment)

### Building the Project

#### Downloading the Source

```sh
git clone https://github.com/inonitz/groundstation.git
cd groundstation
```

#### Configuring & Building

A `build.sh` script is provided to abstract the CMake configuration and Ninja build processes. 

Usage syntax:
`./build.sh <build_type> <library_type> <action>`

Linux / WSL Build Example:

```sh
# Configure the project (includes fetching submodules)
./build.sh release static configure

# Compile the binaries using all available CPU cores
./build.sh release static build
```

<br></br>

## Usage

Once compiled, execute the primary ROS2 nodes required for the Speech-To-Action pipeline.

```sh
# 1. Initialize the Keyboard Hook Node
./llm_to_action_keyboard_hook

# 2. Initialize the ASR Server Node
./llm_to_action_asr_server

# 3. Initialize the Offboard Control Node
./llm_to_action_offboard_mode
```

**Operation:**
To issue a command, hold the **H** key, speak the desired instruction, and release the key. The ASR node processes the audio, and the offboard control node will parse the resulting text to execute the flight maneuver.

<br></br>

## Roadmap & TODO

* **Dynamic Navigation**: Finalize the transition from semantic action scripts to calculated local coordinate vectors.
* **GPS-Free Localization**: Complete the integration of the Stella-VSLAM pipeline and A* algorithm over an OctoMap for dynamic obstacle avoidance.
* **VLM Integration**: Integrate a Vision-Language Model to act as a global semantic supervisor based on the video feed.

<br></br>

## License

Distributed under the GNU GPLv3 License. See `LICENSE` file for more information.

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/inonitz/groundstation?style=for-the-badge&color=blue
[contributors-url]: https://github.com/inonitz/groundstation/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/inonitz/groundstation?style=for-the-badge&color=blue
[forks-url]: https://github.com/inonitz/groundstation/network/members
[stars-shield]: https://img.shields.io/github/stars/inonitz/groundstation?style=for-the-badge&color=blue
[stars-url]: https://github.com/inonitz/groundstation/stargazers
[license-shield]: https://img.shields.io/github/license/inonitz/groundstation?style=for-the-badge
[license-url]: https://github.com/inonitz/groundstation/blob/main/LICENSE
