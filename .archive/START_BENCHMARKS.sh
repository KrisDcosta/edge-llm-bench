#!/bin/bash

cd ~/291_EAI

echo "═══════════════════════════════════════════════════════════════"
echo "M4 Mac Benchmarks - FIXED & READY"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Choose option:"
echo "  1) GPU Only (Metal backend)"
echo "  2) Both GPU and CPU (parallel, recommended for comparison)"
echo ""
read -p "Enter choice [1 or 2]: " choice

if [ "$choice" = "2" ]; then
    echo ""
    echo "Starting both GPU and CPU benchmarks in parallel..."
    echo ""
    
    # Kill any previous results directories to ensure fresh start
    rm -rf results/m4_mac_metal_* results/m4_mac_cpu_*
    
    # Start both in parallel
    bash scripts/benchmark_m4_mac.sh &
    GPU_PID=$!
    
    bash scripts/benchmark_m4_mac_cpu.sh &
    CPU_PID=$!
    
    echo "GPU benchmark running (PID $GPU_PID)"
    echo "CPU benchmark running (PID $CPU_PID)"
    echo ""
    echo "Waiting for completion..."
    wait $GPU_PID $CPU_PID
    echo ""
    echo "✓ Both benchmarks complete!"
    
else
    echo ""
    echo "Starting GPU benchmark..."
    echo ""
    
    # Clean previous results
    rm -rf results/m4_mac_metal_*
    
    bash scripts/benchmark_m4_mac.sh
    echo ""
    echo "✓ GPU benchmark complete!"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Verify results:"
echo "  head -3 results/m4_mac_metal_*/m4_Q2_K_ctx256.jsonl | jq '.decode_tps'"
echo "═══════════════════════════════════════════════════════════════"
