# NEON / Simpleperf Summary

Variants: Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0
Contexts: 256, 512

## Per-Token Counter Table

| Variant | Ctx | Mode | Prompt toks | n | TPS | CV | IPC | Instr/tok | PMU cache-miss proxy/tok | Backend stall % |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q2_K | 256 | filled_context | 113 | 3 | 7.30 | 4.0% | 2.819 | 1392133273 | 770109 | 22.4% |
| Q2_K | 512 | filled_context | 369 | 3 | 5.17 | 9.6% | 2.779 | 1348842490 | 823381 | 23.3% |
| Q3_K_M | 256 | filled_context | 113 | 3 | 4.80 | 1.9% | 2.929 | 1483606880 | 1010297 | 22.3% |
| Q3_K_M | 512 | filled_context | 369 | 3 | 4.24 | 1.4% | 2.933 | 1427253081 | 1007623 | 22.7% |
| Q4_K_S | 256 | filled_context | 113 | 3 | 5.20 | 1.4% | 2.893 | 1165539788 | 1149764 | 16.0% |
| Q4_K_S | 512 | filled_context | 369 | 3 | 4.63 | 1.4% | 2.924 | 1119394558 | 1050036 | 15.6% |
| Q4_K_M | 256 | filled_context | 113 | 3 | 4.63 | 0.4% | 2.921 | 1199663702 | 1159106 | 16.2% |
| Q4_K_M | 512 | filled_context | 369 | 3 | 4.21 | 0.5% | 2.920 | 1159601074 | 1090052 | 16.3% |
| Q5_K_M | 256 | filled_context | 113 | 3 | 3.62 | 0.4% | 2.754 | 1432871058 | 1168617 | 22.9% |
| Q5_K_M | 512 | filled_context | 369 | 3 | 3.31 | 0.5% | 2.744 | 1389298510 | 1175085 | 23.2% |
| Q6_K | 256 | filled_context | 113 | 3 | 3.45 | 0.2% | 2.693 | 1490299859 | 1480535 | 21.4% |
| Q6_K | 512 | filled_context | 369 | 3 | 3.12 | 0.6% | 2.699 | 1449632097 | 1434676 | 21.4% |
| Q8_0 | 256 | filled_context | 113 | 3 | 4.21 | 0.7% | 2.706 | 1061041852 | 2470376 | 28.5% |
| Q8_0 | 512 | filled_context | 369 | 3 | 3.83 | 0.4% | 2.869 | 1030759505 | 1770305 | 25.2% |

## Hypothesis Checks

| Check | Ratio | Expected |
|---|---:|---|
| Q6_K / Q2_K PMU cache-miss proxy per token at ctx=256 | 1.92x | 1.5x to 6.0x, directionally near 3x |
| Q2_K PMU cache-miss proxy ctx=512 / ctx=256 | 1.07x | >=1.5x if cache refill spike explains cliff |
| Q6_K / Q2_K instructions per token at ctx=256 | 1.07x | diagnostic only; do not assume 3x instruction overhead |
| Q8_0 / Q2_K instructions per token at ctx=256 | 0.76x | diagnostic only; cache pressure may dominate instruction count |

## Validation Warnings

- None
