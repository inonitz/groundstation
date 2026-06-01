FROM osrf/ros:jazzy-desktop

ENV DEBIAN_FRONTEND=noninteractive

# Install core tools
RUN apt-get update && apt-get install -y \
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

# Install ROS-Gazebo packages
RUN curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
    && apt-get update && apt-get install -y \
    ros-jazzy-ros-gz \
    gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Install DDS Bridge
RUN git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git \
    && cd Micro-XRCE-DDS-Agent \
    && mkdir build \
    && cd build \
    && cmake .. \
    && make -j $(nproc) \
    && make install \
    && ldconfig

# Setup PX4 source
RUN git clone --recursive https://github.com/PX4/PX4-Autopilot.git
RUN bash PX4-Autopilot/Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools

# Install MAVSDK
RUN git clone https://github.com/mavlink/MAVSDK.git --recursive /root/MAVSDK \
    && cd /root/MAVSDK/cpp \
    && cmake -Bbuild -S. -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j$(nproc) --target install \
    && ldconfig

WORKDIR /root/PX4-Autopilot

RUN make -j$(nproc) px4_sitl
