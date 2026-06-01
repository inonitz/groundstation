xhost +local:root && docker run -it --rm --privileged \
    --env="DISPLAY" \
    --env="QT_X11_NO_MITSHM=1" \
    --env="NVIDIA_DRIVER_CAPABILITIES=all" \
    --env="NVIDIA_VISIBLE_DEVICES=all" \
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
    --gpus all \
    --net=host \
    px4_gazebo-lts-2028_ros2-lts-2029 \
    bash

