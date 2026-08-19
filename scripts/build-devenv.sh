#!/bin/sh
# Build the devenv image, auto-picking the PyTorch backend for THIS host's GPU -- the cross-platform
# knob. Mirrors devenv.sh's detection: NVIDIA -> CUDA, AMD -> ROCm, anything else -> CPU. Build it on
# any machine and torch matches that machine. Override the versions with env vars if needed.
set -eu

IMAGE="${IMAGE:-px4_gazebo-lts-2028_ros2-lts-2029}"
ROCM_VERSION="${ROCM_VERSION:-6.4}"     # download.pytorch.org/whl/rocm<this>
CUDA_VERSION="${CUDA_VERSION:-cu124}"   # download.pytorch.org/whl/<this>
HERE="$(cd "$(dirname "$0")" && pwd)"

if command -v nvidia-smi >/dev/null 2>&1; then
    TORCH_INDEX="https://download.pytorch.org/whl/${CUDA_VERSION}"
    echo "[build-devenv] NVIDIA detected -> PyTorch ${CUDA_VERSION}"
elif [ -e /dev/kfd ]; then
    TORCH_INDEX="https://download.pytorch.org/whl/rocm${ROCM_VERSION}"
    echo "[build-devenv] AMD (/dev/kfd) detected -> PyTorch ROCm ${ROCM_VERSION}"
else
    TORCH_INDEX="https://download.pytorch.org/whl/cpu"
    echo "[build-devenv] no GPU detected -> PyTorch CPU (we'll sort GPU out later)"
fi

echo "[build-devenv] TORCH_INDEX=${TORCH_INDEX}"
exec docker build --build-arg TORCH_INDEX="${TORCH_INDEX}" -t "${IMAGE}" -f "${HERE}/Dockerfile" "${HERE}"
