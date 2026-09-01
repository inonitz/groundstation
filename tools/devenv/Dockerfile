# syntax=docker/dockerfile:1
FROM osrf/ros:jazzy-desktop

ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    iptables \
    conntrack \
    ufw \
    dos2unix \
    netcat-openbsd \
    pulseaudio-utils \
    libasound2-plugins \
    git \
    wget \
    curl \
    ripgrep \
    jq \
    sudo \
    cmake \
    build-essential \
    libcurl4-openssl-dev \
    libssl-dev \
    python3-pip \
    mesa-utils \
    libegl1 \
    libgl1 \
    libvulkan1 \
    libvulkan-dev \
    vulkan-tools \
    clangd \
    clang-format \
    ninja-build \
    tmux \
    libgstreamer1.0-dev \
    gstreamer1.0-tools \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libceres-dev \
    libgoogle-glog-dev \
    libsuitesparse-dev \
    libeigen3-dev \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Cache Gazebo apt packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends \
       ros-jazzy-ros-gz \
       gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

# 1.5 Install RTK and move to PATH
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh \
    && mv /root/.local/bin/rtk /usr/local/bin/rtk

# 1.6 Python ML deps for the llm_cv_scene demo -- baked so containers never refetch (offline-safe).
#     PIP_BREAK_SYSTEM_PACKAGES lets pip work on this externally-managed (PEP 668) base with NO
#     --break-system-packages flag, for the build AND any manual pip you run later.
#     TORCH_INDEX defaults to the CPU wheels: ZERO nvidia/CUDA packages, matching the Vulkan+CPU
#     setup. devenv.sh already passes /dev/kfd + /dev/dri, so to run the detectors on the AMD GPU
#     instead, build with tools/devenv/build-devenv.sh (auto-detects NVIDIA/AMD/CPU) which sets --build-arg TORCH_INDEX for you.
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip pip install --index-url ${TORCH_INDEX} torch torchvision && pip install "numpy<2" "opencv-python<4.12" ultralytics "transformers>=5.15" pillow safetensors lapx requests timm
# 2.7 Pre-bake the open-vocab grounder (LLMDet-tiny) into the image so the demo runs fully OFFLINE
#     (no HuggingFace fetch at show time). Weights are backend-agnostic -> vendor-neutral. Keep this
#     checkpoint in sync with config.GROUNDER_REPO in archive/llm_cv_scene/config.py.
RUN python3 -c "from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection as M; r='iSEE-Laboratory/llmdet_tiny'; AutoProcessor.from_pretrained(r); M.from_pretrained(r); print('baked '+r)"

# 3. Define VS Code Environment Variables
ENV VSCodeClangdAbsPath=/usr/bin/clangd
ENV VSCodeClangdQueryDriverAbsPath=/usr/bin/g++
ENV VSCodeClangFormatAbsPath=/usr/bin/clang-format

WORKDIR /root

# 4. Shallow clone DDS
RUN git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git \
    && cd Micro-XRCE-DDS-Agent \
    && mkdir build && cd build \
    && cmake .. \
    && make -j $(nproc) \
    && make install \
    && ldconfig

# # 5. Shallow clone MAVSDK
# RUN git clone --depth 1 --recursive --shallow-submodules https://github.com/mavlink/MAVSDK.git /root/MAVSDK \
#     && cd /root/MAVSDK/cpp \
#     && cmake -Bbuild -S. -DCMAKE_BUILD_TYPE=Release \
#     && cmake --build build -j$(nproc) --target install \
#     && ldconfig

# 6. Shallow clone & Build PX4
RUN git clone --depth 1 --recursive --shallow-submodules https://github.com/PX4/PX4-Autopilot.git
RUN bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools

WORKDIR /root/PX4-Autopilot
RUN make -j$(nproc) px4_sitl

# 7. Shallow clone & Build px4_msgs natively with Ninja
WORKDIR /opt/px4_ws

RUN git clone --depth 1 https://github.com/PX4/px4_msgs.git src/px4_msgs \
    && bash -c "source /opt/ros/jazzy/setup.bash && colcon build --cmake-args -G Ninja"

# 8. Setup Bash environment
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "source /opt/px4_ws/install/setup.bash" >> /root/.bashrc \
    && echo 'export PX4_SIM_HOST_ADDR=$(ip route show | awk "/default/ {print \$3}")' >> /root/.bashrc

WORKDIR /root

RUN git config --global --add safe.directory '*'
RUN git config --global --add safe.directory /root/groundstation
RUN git config --global --add safe.directory /root/groundstation/dependencies