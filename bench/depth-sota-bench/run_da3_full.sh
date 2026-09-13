#!/bin/bash
cd "$(dirname "$0")"
CPU=depth-anything.cpp/build-cpu/examples/cli/da3-cli
VK=depth-anything.cpp/build-vk/examples/cli/da3-cli
IMG=test.png; REP=15
: > results_da3_full.txt
row() { printf '%-42s %s\n' "$1" "$2" | tee -a results_da3_full.txt; }
cpu() { line=$("$CPU" depth --model "gguf/$1.gguf" --input "$IMG" --repeat "$REP" --threads 16 2>/dev/null | grep -m1 '^bench:'); row "$2 CPU-16t" "$line"; }
vk()  { line=$("$VK"  depth --model "gguf/$1.gguf" --input "$IMG" --repeat "$REP" 2>/dev/null | grep -m1 '^bench:'); row "$2 GPU-vk" "${line:-CRASH/none}"; }
# CPU: everything
cpu depth-anything-base-q4_k              "DA3 base q4_k (rel)"
cpu depth-anything-base-q8_0              "DA3 base q8_0 (rel)"
cpu depth-anything-base-f16               "DA3 base f16 (rel)"
cpu depth-anything-large-f32             "DA3 large f32 (rel)"
cpu depth-anything-metric-large-f32      "DA3 metric-large f32"
cpu depth-anything-metric-large-q8_0     "DA3 metric-large q8_0"
cpu depth-anything-metric-large-q4_k     "DA3 metric-large q4_k"
cpu depth-anything2-base-q8_0            "DA2 base q8_0 (rel)"
cpu depth-anything2-large-q8_0          "DA2 large q8_0 (rel)"
cpu depth-anything2-metric-hypersim-large-q4_k "DA2 metric-large q4_k"
cpu depth-anything2-metric-hypersim-large-q8_0 "DA2 metric-large q8_0"
# Vulkan GPU: large models (base crashes)
vk depth-anything-large-f32             "DA3 large f32 (rel)"
vk depth-anything-metric-large-f32      "DA3 metric-large f32"
vk depth-anything-metric-large-q8_0     "DA3 metric-large q8_0"
vk depth-anything-metric-large-q4_k     "DA3 metric-large q4_k"
vk depth-anything2-large-q8_0          "DA2 large q8_0 (rel)"
vk depth-anything2-metric-hypersim-large-q4_k "DA2 metric-large q4_k"
vk depth-anything2-metric-hypersim-large-q8_0 "DA2 metric-large q8_0"
echo "DA3_FULL DONE"
