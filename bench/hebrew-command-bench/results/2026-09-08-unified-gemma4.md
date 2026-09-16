# Gemma 4 alone through harden2's unified call, every set (re-scored 18:05)

| set | Gemma 4 alone, harden2 unified call | Hy-MT2 -> Qwen, harden (488 gate) |
|---|---|---|
| emergency | 12/12 | 12/12 |
| std190 | 236/253 | 247/253 |
| verbose | 59/63 | 51/63 |
| perception | 108/138 | 100/138 |
| military | 0/21 | 10/21 |
| ALL | 415/487 | 420/487 |
| ALL without military | 415/466 | 410/466 |

Military (21 slang idioms) scores a TRANSLATION by keywords; the unified call has none (it routes them to reject/mission/describe), so that set is not comparable for harden2.
Perception: the keyword groups are applied to '<kind words> the <target_en>'; kind words: highlight -> highlight/find/mark/follow/track/focus, count -> count/how many, describe -> describe/tell/what/see/look/scene/area/frame/image.
Commands: 295/316 vs 298/316. The unified prompt costs Gemma 9 std cases against its planner-only lane (245/253): 6 rejects, 3 wrong routes.
latency per case: p50 475 ms, p95 1010 ms (one call does routing + planning + the SAM3 phrase).
