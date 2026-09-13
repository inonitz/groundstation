#!/bin/bash
cd "$(dirname "$0")"
CPU=depth-anything.cpp/build-cpu/examples/cli/da3-cli
VK=depth-anything.cpp/build-vk/examples/cli/da3-cli
IMG=test.png; REP=15
: > results_da3cpp.txt
run() { # $1=bin $2=modelfile $3=label $4=extra-args
  line=$("$1" depth --model "gguf/$2" --input "$IMG" --repeat "$REP" $4 2>/dev/null | grep -m1 '^bench:')
  printf '%-34s %s\n' "$3" "$line" | tee -a results_da3cpp.txt
}
for m in depth-anything-base-q4_k depth-anything-base-q8_0 depth-anything-base-f16 depth-anything-metric-large-f32; do
  run "$CPU" "$m.gguf" "$m CPU-2t"  "--threads 2"
  run "$CPU" "$m.gguf" "$m CPU-8t"  "--threads 8"
  run "$CPU" "$m.gguf" "$m CPU-16t" "--threads 16"
  run "$VK"  "$m.gguf" "$m GPU-vulkan" ""
done
echo "DA3CPP DONE"
