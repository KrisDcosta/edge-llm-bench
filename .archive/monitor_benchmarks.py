#!/usr/bin/env python3
"""Monitor the progress of quality evaluation benchmarks."""
import json
import time
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("/Users/krisdcosta/291_EAI")
RESULTS_FILE = PROJECT_ROOT / "results" / "quality_metrics_m4.json"

def monitor():
    """Monitor benchmark progress."""
    print("Monitoring quality evaluation benchmarks...")
    print(f"Results file: {RESULTS_FILE}")
    print("Press Ctrl+C to stop monitoring\n")

    last_count = 0

    while True:
        try:
            if RESULTS_FILE.exists():
                with open(RESULTS_FILE) as f:
                    results = json.load(f)

                current_count = len(results)

                if current_count > last_count:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {current_count} result(s) recorded")

                    # Show latest results
                    for key in list(results.keys())[-3:]:
                        result = results[key]
                        if result.get("status") == "success":
                            acc = result.get("accuracy_pct", "N/A")
                            correct = result.get("correct", 0)
                            total = result.get("total", 0)
                            print(f"  ✓ {key}: {acc}% ({correct}/{total})")

                    last_count = current_count

            time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            print("\nMonitoring stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    monitor()
