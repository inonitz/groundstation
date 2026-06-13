Write-Host "Firing up Gazebo in WSL2..." -ForegroundColor Cyan

# $dockerArguments = @(
#     "docker run --rm -it",
#     "--device /dev/dxg",
#     "-v /usr/lib/wsl/lib:/usr/lib/wsl/lib",
#     "-v /usr/lib/wsl/drivers:/usr/lib/wsl/drivers",
#     "-v /usr/lib/wsl/lib/libdxcore.so:/usr/lib/x86_64-linux-gnu/libdxcore.so.1",
#     "-e LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers",
#     '-e DISPLAY=$DISPLAY',
#     "-v /tmp/.X11-unix:/tmp/.X11-unix",
#     "-e MESA_LOADER_DRIVER_OVERRIDE=d3d12",
#     "-e GALLIUM_DRIVER=d3d12",
#     "-e MESA_D3D12_DEFAULT_ADAPTER_NAME=AMD",
#     "-e LIBGL_ALWAYS_SOFTWARE=0",
#     "px4_gazebo-lts-2028_ros2-lts-2029 bash -c 'make px4_sitl gz_x500'"
# )

$dockerArguments = @(
    "docker run --rm -it",
    "--device /dev/dxg",
    
    # GPU Driver Mounts
    "-v /usr/lib/wsl/lib:/usr/lib/wsl/lib",
    "-v /usr/lib/wsl/drivers:/usr/lib/wsl/drivers",
    "-v /usr/lib/wsl/lib/libdxcore.so:/usr/lib/x86_64-linux-gnu/libdxcore.so.1",
    
    # GPU Environment Variables
    "-e LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers",
    "-e MESA_LOADER_DRIVER_OVERRIDE=d3d12",
    "-e GALLIUM_DRIVER=d3d12",
    "-e MESA_D3D12_DEFAULT_ADAPTER_NAME=AMD",
    "-e LIBGL_ALWAYS_SOFTWARE=0",
    
    # WSLg Display Mounts (X11 & Wayland)
    "-v /tmp/.X11-unix:/tmp/.X11-unix",
    "-v /mnt/wslg:/mnt/wslg",
    '-e DISPLAY=$DISPLAY',          # Hardcoded to WSLg's default X11 display
    "-e WAYLAND_DISPLAY=wayland-0", # WSLg's default Wayland display
    "-e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir",
    
    # The Image and Execution Command
    "px4_gazebo-lts-2028_ros2-lts-2029 bash -c 'make px4_sitl gz_x500'"
)


$dockerCmd = $dockerArguments -join ' '
wsl --exec bash -c $dockerCmd
