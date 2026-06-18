#!/bin/bash

# Define automatic cleanup function
cleanup() {
    echo "Killing remaining simulation processes..."
    pkill -9 -f px4
    pkill -9 -f ruby
}

# Catch SIGINT (Ctrl+C), SIGTERM, and shell exit
trap cleanup SIGINT SIGTERM EXIT

# Start simulation
cd /root/PX4-Autopilot/ && make px4_sitl gz_x500