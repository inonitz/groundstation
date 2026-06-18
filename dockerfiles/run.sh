#!/bin/bash

# 1. Start MicroXRCEAgent
gnome-terminal -- sh -c "MicroXRCEAgent udp4 -p 8888; exec bash"

# 2. Start PX4 SITL Gazebo, use CTRL+C/Close the Terminal for proper cleanup
gnome-terminal -- sh -c "cd ~/groundstation/dockerfiles && ./launch_with_cleanup.sh"

