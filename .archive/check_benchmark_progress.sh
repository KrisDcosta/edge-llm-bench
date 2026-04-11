#!/bin/bash

# Real-time benchmark progress checker
# Usage: bash check_benchmark_progress.sh

RESULTS_DIR="results/m4_mac_metal_20260317_035638"

if [ ! -d "$RESULTS_DIR" ]; then
  echo "ERROR: Results directory not found"
  exit 1
fi

while true; do
  clear
  
  # Count total records
  total=0
  for f in "$RESULTS_DIR"/*.jsonl; do
    [ -f "$f" ] && total=$((total + $(grep -c "^{" "$f" 2>/dev/null || echo 0)))
  done
  
  percent=$((total * 100 / 420))
  elapsed=$(($(date +%s) - $(stat -f%B "$RESULTS_DIR" 2>/dev/null || echo 0)))
  
  echo "╔════════════════════════════════════════════════════╗"
  echo "║     M4 MAC METAL BENCHMARK PROGRESS MONITOR        ║"
  echo "╚════════════════════════════════════════════════════╝"
  echo ""
  echo "Progress: $total / 420 records ($percent%)"
  echo "Elapsed: $(($elapsed / 60)) minutes"
  
  if [ $percent -gt 0 ]; then
    rate=$(echo "scale=2; $elapsed / $total" | bc)
    remaining=$(echo "scale=0; ($rate * (420 - $total)) / 60" | bc)
    echo "Estimated remaining: ~$remaining minutes"
  fi
  
  echo ""
  echo "Completed variants:"
  for variant in Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0; do
    completed_ctxs=0
    for ctx in 256 512 1024 2048; do
      f="$RESULTS_DIR/m4_${variant}_ctx${ctx}.jsonl"
      if [ -f "$f" ]; then
        count=$(grep -c "^{" "$f" 2>/dev/null || echo 0)
        [ $count -eq 15 ] && completed_ctxs=$((completed_ctxs + 1))
      fi
    done
    [ $completed_ctxs -gt 0 ] && echo "  ✓ $variant: $completed_ctxs/4 contexts done"
  done
  
  echo ""
  
  if [ $total -ge 420 ]; then
    echo "✅ BENCHMARK COMPLETE!"
    break
  fi
  
  echo "Press Ctrl+C to stop monitoring"
  sleep 30
done
