# syntax=docker/dockerfile:1
FROM osrf/ros:jazzy-desktop

ENV DEBIAN_FRONTEND=noninteractive

# Cache apt packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    sudo \
    cmake \
    build-essential \
    libcurl4-openssl-dev \
    libssl-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Cache Gazebo apt packages
# (Cache Gazebo apt packages)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends \
       ros-jazzy-ros-gz \
       gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Shallow clone DDS
RUN git clone --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git \
    && cd Micro-XRCE-DDS-Agent \
    && mkdir build && cd build \
    && cmake .. \
    && make -j $(nproc) \
    && make install \
    && ldconfig

# Shallow clone PX4
RUN git clone --depth 1 --recursive --shallow-submodules https://github.com/PX4/PX4-Autopilot.git
RUN bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools

# Shallow clone MAVSDK
RUN git clone --depth 1 --recursive --shallow-submodules https://github.com/mavlink/MAVSDK.git /root/MAVSDK \
    && cd /root/MAVSDK/cpp \
    && cmake -Bbuild -S. -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j$(nproc) --target install \
    && ldconfig

# Build PX4
WORKDIR /root/PX4-Autopilot
RUN make -j$(nproc) px4_sitl

# Add Optional Dependencies required for windows
RUN apt-get update && apt-get install -y \
    mesa-utils \
    libegl1 \
    libgl1 \
    libvulkan1


# px4_msgs Is a dependency required for the project
WORKDIR /opt/px4_ws

RUN git clone https://github.com/PX4/px4_msgs.git src/px4_msgs \
    && bash -c "source /opt/ros/jazzy/setup.bash && colcon build"

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc \
    && echo "source /opt/px4_ws/install/setup.bash" >> /root/.bashrc

WORKDIR /root