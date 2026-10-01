# Recognizer accuracy, gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf, thinking off

2026-09-28 04:05; wall 349 s.

| set | cases | PASS | FAIL | REVIEW |
|---|---|---|---|---|
| commands | 254 | 241 | 13 | 0 |
| emergency | 12 | 12 | 0 | 0 |
| live-test-50 | 50 | 32 | 0 | 18 |
| live-test-75 | 75 | 49 | 3 | 23 |
| live-test-e2e-50 | 50 | 44 | 4 | 2 |
| live-test-subset | 26 | 25 | 1 | 0 |
| military | 21 | 0 | 21 | 0 |
| numbers | 40 | 37 | 3 | 0 |
| perception | 138 | 102 | 36 | 0 |
| verbose | 63 | 59 | 4 | 0 |
| ALL | 729 | 601 | 85 | 43 |

route() per case: P50 514 ms, P95 1016 ms, max 2079 ms.
