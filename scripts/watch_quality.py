#!/usr/bin/env python3
"""
watch_quality.py — live progress tracker for quality_eval.py runs
Usage: py -3 scripts/watch_quality.py x86_hellaswag
       py -3 scripts/watch_quality.py x86_mmlu
"""
import json, time, os, sys

tag = sys.argv[1] if len(sys.argv) > 1 else "x86_hellaswag"
variants = ['Q2_K', 'Q3_K_M', 'Q4_K_S', 'Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0']
last = {}

print(f"Watching tag: {tag}  (refreshes every 20s, Ctrl+C to stop)\n")

while True:
    try:
        d = json.load(open('C:/Users/Kris/291_EAI/results/quality_scores.json'))
        done = {
            k.split(':')[1]: v
            for k, v in d.items()
            if k.startswith(tag + ':') and v.get('status') == 'success'
        }
        if done != last:
            os.system('cls')
            print(f"{tag}  {len(done)}/7 complete\n")
            print(f"{'Variant':<12} {'Accuracy':>10} {'Correct':>9}")
            print('-' * 35)
            for v in variants:
                if v in done:
                    r = done[v]
                    print(f"{v:<12} {str(r['accuracy_pct']) + '%':>10} {str(r['correct']) + '/100':>9}")
                else:
                    idx = len(done)
                    label = 'running...' if idx < len(variants) and v == variants[idx] else 'waiting'
                    print(f"{v:<12} {label:>10}")
            if len(done) == 7:
                print('\nCOMPLETE')
                break
            last = done
    except Exception:
        pass
    time.sleep(20)
