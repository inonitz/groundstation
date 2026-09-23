# Exception audit — integration_harden2 (2026-09-20)

## Objective

List every raise, try, except and finally in integration_harden2. Classify each against the house
rule: no exceptions in our own code; crash via die(); try/except only to wrap a third-party API and
convert to a status code.

## Totals

| token | count | note |
|---|---|---|
| raise (with argument) | 9 | grep "raise " |
| raise (bare re-raise) | 2 | dji_wire.py:59, :92, not caught by the grep above |
| try | 72 | ast-counted |
| except handlers | 71 | ast-counted; the grep 77 included the word in comments/docstrings |
| finally | 3 | mvd.py (teardown), live_mock_smoke.py |

## Category 1 — our own raises (the ones the rule targets)

### 1a. Runtime path, VIOLATIONS (must go)

| site | raise | what it buys us | caught by | fix |
|---|---|---|---|---|
| control/dji_wire.py:33 | RuntimeError, non-loopback host without allow_real | safety guard: refuses a real-drone target | mvd.py:457 | die() (fatal safety invariant) |
| control/dji_wire.py:59 | bare re-raise of a urllib error in _post | aborts a discrete verb on an unreachable backend | mvd.py:228 | return a status code |
| control/dji_wire.py:92 | bare re-raise of a urllib error in _post_json | aborts a mission on an unreachable backend | mvd.py:228 | return a status code |
| audio/tts_io.py:124 | RuntimeError, aplay returncode | signals aplay failed | tts_io.py:106 | log in place and return |

### 1b. Allowed raises (NOT the runtime path; they stay)

| site | raise | why allowed |
|---|---|---|
| perception/engine.py:210 | SystemExit(1) | __main__ self-test exit |
| perception2/concept.py:244 | SystemExit(1) | __main__ self-test exit |
| perception2/sam3_backend.py:153 | SystemExit(_smoke()) | __main__ smoke exit |
| recognizer/selftest.py:119 | SystemExit(1) | self-test exit |
| perception2/concept.py:234 | RuntimeError("server down") | test fixture inside selftest(), simulates a failing VLM |
| test/test_crash_safety.py:95 | SystemExit(pytest.main(...)) | test entry point |

Note: audio/tts_io.py already uses die() (not raise) for fatal phonikud misconfig at lines 47, 49, 52, 57.

## Category 2 — catches of our OWN raises (VIOLATIONS, go with the raise)

| catch site | catches | after the fix |
|---|---|---|
| mvd.py:457 (setup_drone_router) | dji_wire.py:33 RuntimeError | from_env die()s or returns None; main reads a status |
| mvd.py:228 (router.handle) | dji_wire.py:59/92 re-raise | fly_mission returns a code; the caller reads it |
| tts_io.py:106 (_worker) | tts_io.py:124 RuntimeError | no raise; the catch keeps only the third-party aplay throw |

## Category 3 — grey zone: catches around OUR callable that wraps third-party

These do not catch an explicit raise of ours. They wrap an injected callable that calls a third-party
model or HTTP. The throw is third-party; the catch is not at the raw boundary. Tighten later if wanted.

| site | wraps | on failure |
|---|---|---|
| mvd.py:314 (_gate_thread) | ENGINE.detect (SAM3) | empty gate |
| mvd.py:327 (_gate_thread) | verify_highlight (SAM3) | fail-open, gate stands |
| mvd.py:254 (_count_thread) | ENGINE.detect loop (SAM3) | count fails, logs |
| perception/engine.py:99 | mask_for_box (SAM3) | skip the mask |
| perception/engine.py:117 | detect (SAM3) | no highlight |
| perception/engine.py:135 | vlm_ask (VLM HTTP) | no box |
| audio/phone_asr.py:55 | on_text callback | keep the socket alive |

## Category 4 — third-party / stdlib / import catches (ALLOWED, 67 total)

The rule permits these: each wraps a third-party or stdlib call and converts it to a status, a fallback,
or a log. Grouped by file.

| file | sites | wraps |
|---|---|---|
| control/dji_wire.py | 27, 56, 89 | ipaddress parse (ValueError), urllib HTTPError -> status code |
| audio/tts_io.py | 19, 53, 81, 83, 92, 93, 97, 99, 102, 103, 105 | requests import, phonikud import (->die), subprocess, queue.Empty |
| audio/phone_asr.py | 41, 62, 100, 106, 118 | json parse, asyncio server, socket close |
| audio/ros2_asr.py | 32 | rclpy shutdown |
| video/camera_stream.py | 18, 34, 36, 38, 77, 126, 134 | rclpy import, ROS2 spin/teardown, numpy on external msg |
| perception/detectors.py | 35 | YOLO predict |
| perception/vlm_client.py | 19, 105 | requests health + chat |
| perception2/concept.py | 124, 151, 192 | json.load, VLM ask -> offline fallback |
| recognizer/llama.py | 32, 63, 89 | urllib health, subprocess wait, urllib chat |
| recognizer/pipeline.py | 21, 29, 141 | optional imports, json parse of model output |
| session_log.py | 70, 108, 125, 148, 164, 176, 180 | file I/O (all best-effort logging) |
| overlay.py | 22, 30, 33 | PIL / bidi import + font load |
| config/defaults.py | 18, 95, 114 | subprocess ip route, torch import, /proc/net/route read |
| cam_list.py | 9 | cv2 import |
| mvd.py | 32, 143, 277, 352 | Ears import, SAM3 model load, voice.say, vlm.ask |
| mvd.py (helpers) | 382, 409, 468, 475 | SessionLog, Voice, Ears, PhoneEars init -> status None |

## Analysis

1. The whole project has only FOUR raise sites in the runtime path. All four are in two files.
2. Two files hold every runtime violation: control/dji_wire.py and audio/tts_io.py.
3. Three catch sites exist only to catch our own raises: mvd.py:457, mvd.py:228, tts_io.py:106.
4. CORRECTION to the prior report: the dji_wire re-raise is NOT uncaught. It propagates through
   router.handle to mvd.py:228, which reports "drone unreachable". My earlier "uncaught" was wrong.
5. Everything else (67 catches) wraps a third-party or stdlib call. The rule allows these.
6. Seven catches sit in a grey zone: they wrap our injected callables that call third-party models.
7. session_log.py is the largest single cluster: seven file-I/O catches, all best-effort logging.

## Conclusion

To satisfy the rule, change FOUR raise sites and THREE catch sites, in two files plus mvd:
- dji_wire.py: :33 -> die(); :59 and :92 -> return a status code.
- tts_io.py: :124 -> log and return; the catch at :106 then holds only the aplay third-party throw.
- mvd.py: :457 reads a status from from_env; :228 reads the mission code instead of catching.

The grey-zone seven (Category 3) are a separate, optional decision, not rule violations.

## Full enumeration (ast, every try block, none skipped)

```
 1. audio/phone_asr.py:41  try: return str(json.loads(raw).get('text', '')).strip()
      except Exception@43
 2. audio/phone_asr.py:55  try: self._on_text(text)
      except Exception@57
 3. audio/phone_asr.py:62  try: first = await reader.readline()
      except Exception@98
 4. audio/phone_asr.py:100  try: writer.close()
      except Exception@101
 5. audio/phone_asr.py:106  try: coro = asyncio.start_server(self._handle, self.host, self.port)
      except Exception@109
 6. audio/phone_asr.py:118  try: self._loop.call_soon_threadsafe(self._loop.stop)
      except Exception@120
 7. audio/ros2_asr.py:29  try: self._node.destroy_node()
      except Exception@32
 8. audio/tts_io.py:19  try: import requests
      except Exception@21
 9. audio/tts_io.py:53  try: from phonikud_onnx import Phonikud
      except Exception@57
10. audio/tts_io.py:81  try: while True:
      except queue.Empty@83
11. audio/tts_io.py:92  try: p.terminate()
      except Exception@93
12. audio/tts_io.py:97  try: text = self._q.get(timeout=0.2)
      except queue.Empty@99
13. audio/tts_io.py:102  try: self._say_phone(text)
      except Exception@103
14. audio/tts_io.py:105  try: self._say_phonikud(text)
      except Exception@106
15. cam_list.py:7  try: import cv2
      except Exception@9
16. config/defaults.py:14  try: for line in subprocess.run(['ip', 'route'], capture_output=True,
      except Exception@18
17. config/defaults.py:88  try: import torch
      except Exception@95
18. config/defaults.py:109  try: for line in open('/proc/net/route').readlines()[1:]:
      except Exception@114
19. control/dji_wire.py:25  try: return ipaddress.ip_address(host).is_loopback
      except ValueError@27
20. control/dji_wire.py:52  try: with urllib.request.urlopen(req, timeout=self.timeout) as r:
      except urllib.error.HTTPError@56 | except Exception@59
21. control/dji_wire.py:85  try: with urllib.request.urlopen(req, timeout=self.timeout) as r:
      except urllib.error.HTTPError@89 | except Exception@92
22. mvd.py:30  try: from audio.ros2_asr import Ears
      except Exception@32
23. mvd.py:141  try: OM['det'] = make()
      except Exception@143
24. mvd.py:182  try: if self._handle_drone(text):
       +finally
25. mvd.py:226  try: res = self.router.handle(text)
      except Exception@228
26. mvd.py:254  try: frame = fr
      except Exception@266
27. mvd.py:276  try: self.voice.say(f'יש {n}' if n else 'לא מצאתי')
      except Exception@277
28. mvd.py:311  try: gate_raw = ENGINE['e'].detect(fr, concepts, 0.1)
      except Exception@314
29. mvd.py:319  try: from perception2.verify import split_target, verify_highlight
      except Exception@327
30. mvd.py:351  try: desc, _, _, spoken = vlm.ask(fr, q, [])
      except Exception@352
31. mvd.py:380  try: return SessionLog()
      except Exception@382
32. mvd.py:407  try: return Voice()
      except Exception@409
33. mvd.py:421  try: wire = DjiWire.from_env()
      except Exception@457
34. mvd.py:465  try: ears = Ears(on_text)
      except Exception@468
35. mvd.py:472  try: from audio.phone_asr import PhoneEars
      except Exception@475
36. mvd.py:664  try: run_display_loop(cap, win, source)
       +finally
37. overlay.py:16  try: from PIL import Image, ImageDraw, ImageFont
      except Exception@33
38. overlay.py:21  try: return ImageFont.truetype(path, sz) if os.path.exists(path) else
      except Exception@22
39. overlay.py:27  try: from PIL import features as _pil_features
      except Exception@30
40. perception/detectors.py:30  try: if self._bg is None:
      except Exception@35
41. perception/engine.py:99  try: mask = self.mask_for_box(frame, d['box'])
      except Exception@101
42. perception/engine.py:117  try: raw = self.detect(frame, target, self.floor)
      except Exception@119
43. perception/engine.py:135  try: _, target, box, _ = self.vlm_ask(frame, f'Point at and highlight
      except Exception@137
44. perception/vlm_client.py:12  try: r = requests.get(config.LLAMA_URL + '/health', timeout=2)
      except Exception@19
45. perception/vlm_client.py:101  try: r = requests.post(config.LLAMA_URL + '/v1/chat/completions', jso
      except Exception@105
46. perception2/concept.py:122  try: _LEARNED.update(json.load(open(path)))
      except Exception@124
47. perception2/concept.py:145  try: concepts = _parse_vlm(ask(CONCEPT_PROMPT.format(phrase=phrase)))
      except Exception@151
48. perception2/concept.py:188  try: r = requests.post(base + '/v1/chat/completions', json=body, time
      except Exception@192
49. recognizer/llama.py:29  try: urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeou
      except Exception@32
50. recognizer/llama.py:61  try: self.proc.wait(timeout=15)
      except Exception@63
51. recognizer/llama.py:86  try: with urllib.request.urlopen(req, timeout=180) as r:
      except urllib.error.HTTPError@89
52. recognizer/pipeline.py:19  try: from perception2.lexicon import fix_target
      except Exception@21
53. recognizer/pipeline.py:24  try: from .llama import chat
      except ImportError@29
54. recognizer/pipeline.py:139  try: return json.loads(m.group(0))
      except Exception@141
55. session_log.py:61  try: _atomic_json(os.path.join(self.dir, 'meta.json'), {'session': os
      except Exception@70
56. session_log.py:103  try: with self._lock:
      except Exception@108
57. session_log.py:116  try: cand = [w for w in sorted(glob.glob(os.path.join(self.clips_dir,
      except Exception@125
58. session_log.py:133  try: seq = self.cur_seq()
      except Exception@148
59. session_log.py:153  try: with self._lock:
      except Exception@164
60. session_log.py:168  try: with self._lock:
      except Exception@180
61. session_log.py:174  try: j = json.load(open(rp))
      except Exception@176
62. test/live_mock_smoke.py:38  try: status()
      except Exception@41
63. test/live_mock_smoke.py:50  try: assert wait_up(), f'mock did not come up -- see {log.name}'
       +finally
64. test/live_mock_smoke.py:82  try: proc.wait(timeout=3)
      except Exception@84
65. test/test_router.py:92  try: fn()
      except AssertionError@93
66. video/camera_stream.py:14  try: import rclpy
      except Exception@18
67. video/camera_stream.py:33  try: spin.join(timeout=1.5)
      except Exception@34
68. video/camera_stream.py:35  try: executor.remove_node(node)
      except Exception@36
69. video/camera_stream.py:37  try: node.destroy_node()
      except Exception@38
70. video/camera_stream.py:74  try: while not self._stop and rclpy.ok():
      except Exception@77
71. video/camera_stream.py:123  try: while not self._stop and rclpy.ok():
      except Exception@126
72. video/camera_stream.py:131  try: arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(h, 
      except Exception@134

TOTAL try blocks: 72   TOTAL except handlers: 71
```
