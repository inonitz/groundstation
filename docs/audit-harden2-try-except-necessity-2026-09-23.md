# Audit: is each try/except in integration_harden2 necessary? (2026-09-23)

## Objective

The house rule allows a try/except only around a third-party call that throws, and only when no
non-throwing alternative exists. This audit checks each try block in
`projects/integration_harden2` against that rule. It finds the non-throwing alternative where one
exists. It names blocks that can merge into one shared helper.

## Setup

- Inventory command: `grep -rn --include=*.py -E '^\s*try:' /root/groundstation/projects/integration_harden2 | grep -v /test/`.
- The command returns **29** blocks, not 28.
- Each block was read in context.
- Throw behavior was checked against the official docs (URLs in the table).
- The rclpy and asyncio claims were also checked against the installed source (ROS 2 Jazzy, Python 3.12). Local probes were run too.
- Local probe results:
  - `Executor.remove_node` on a node the executor does not hold returns without error.
  - A second `Node.destroy_node()` returns without error.
  - A second `rclpy.try_shutdown()` returns without error.
  - A second `rclpy.shutdown()` raises RuntimeError.
  - `Thread.join()` on a thread that was never started raises RuntimeError.
  - `socket.connect_ex` returns 111 (ECONNREFUSED) for a closed port. It returns 11 (EAGAIN) on a timeout. It does not raise in either case.
- No code was changed.

## Results

Verdict key:
- UNAVOIDABLE: no non-throwing API exists, so the block stays.
- REPLACEABLE: a non-throwing API or check replaces the block.
- MERGEABLE: the block is needed, but it moves into one shared helper.
- REMOVE: the call cannot throw here, or the crash hook already gives the same result.

"Own code?" asks whether the block catches an exception from our own code. A "yes" breaks the rule outright.

| # | file:line | What throws | Non-throwing alternative | Own code? | Broad? (narrower type) | Merge | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | gemma/server.py:40 | `urllib.request.urlopen` /health. It raises URLError (an OSError) when the server is down. It raises HTTPError while the server still loads (503). | None in the stdlib. `http.client.HTTPConnection.getresponse()` returns 4xx/5xx as a status, but a refused connection still raises OSError ([http.client](https://docs.python.org/3/library/http.client.html#http.client.HTTPConnection.getresponse), [urllib.error](https://docs.python.org/3/library/urllib.error.html)). `requests` also raises on connect failure ([requests](https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions)). | no | no. URLError is a subclass of OSError, so `OSError` alone covers it. | HTTP helper | MERGEABLE |
| 2 | gemma/server.py:82 | `Popen.wait(timeout=15)` raises TimeoutExpired. | Yes. Poll in a loop: `Popen.poll()` never raises and returns None while the child runs. Then kill and wait with no timeout ([subprocess](https://docs.python.org/3/library/subprocess.html#subprocess.Popen.poll)). | no | no | shared `stop_proc(proc, grace_s)` with #20 | REPLACEABLE (0 try) |
| 3 | gemma/client.py:36 | `urlopen` plus `r.read()`. They raise URLError/OSError/timeout and http.client.HTTPException (for example IncompleteRead). | None. The reason is the same as #1. | no | no. URLError is redundant with OSError. | HTTP helper | MERGEABLE |
| 4 | gemma/client.py:42 | `json.loads` raises JSONDecodeError. | None. The stdlib json has no non-throwing parser ([json](https://docs.python.org/3/library/json.html#json.loads)). orjson also raises JSONDecodeError ([orjson](https://github.com/ijl/orjson#deserialize)). ujson and simdjson raise ValueError. | no | no | JSON helper | MERGEABLE |
| 5 | session_log.py:52 | `open`/`json.dump`/`fsync`/`os.replace` raise OSError. | None. `open` raises OSError on failure ([open](https://docs.python.org/3/library/functions.html#open)). An `os.access` pre-check is racy and misses a full disk. | no | no | FS helper (`atomic_write`) | MERGEABLE |
| 6 | session_log.py:70 | `os.replace` raises OSError. | None ([os.replace](https://docs.python.org/3/library/os.html#os.replace)). `cv2.imencode` returns `(ok, buf)` and never raises on a failed encode ([imencode](https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html)). So the JPEG path can become imencode followed by the same `atomic_write` as #5. | no | no | FS helper (`atomic_write`) | MERGEABLE |
| 7 | session_log.py:167 | `open(..., "a")`/`write`/`fsync` raise OSError. | None | no | no | FS helper (`append_line`) with #13 | MERGEABLE |
| 8 | session_log.py:186 | `os.rename` raises OSError. | None | no | no | FS helper (`rename`) | MERGEABLE |
| 9 | fatal.py:34 | Any registered die() cleanup, for example `supervisor.stop_all`. | None. This is the crash path: if a cleanup throws, `os._exit(1)` must still run. | **yes**. It catches our own cleanup functions. | **yes**, `except Exception`. This is broad on purpose, because the crash path must survive anything. | -- | UNAVOIDABLE by design. Keep it as the one documented exception to the rule. |
| 10 | video/camera_stream.py:43 | `Thread.join(timeout)`. It raises RuntimeError only if the thread was never started or is the current thread ([threading](https://docs.python.org/3/library/threading.html#threading.Thread.join)). | Not needed. `__init__` always starts the thread, and `release()` never runs on the spin thread. The call cannot throw here. | **yes**. The only throw would come from our own misuse. | **yes**, `except Exception` | -- | REMOVE |
| 11 | video/camera_stream.py:47 | `executor.remove_node`. | Not needed. In the Jazzy source it catches KeyError itself and returns (probe confirmed). | no | **yes**, `except Exception` | -- | REMOVE |
| 12 | video/camera_stream.py:51 | `node.destroy_node`. | Not needed. The probe showed a second call is a no-op. An rcl-level failure here is a real fault and should reach the crash hook. | no | **yes**, `except Exception` | -- | REMOVE |
| 13 | recognizer/trace.py:29 | `open(..., "a")`/`write` raise OSError. | None | no | no | FS helper (`append_line`) with #7 | MERGEABLE |
| 14 | recognizer/pipeline.py:22 | ImportError from our own relative imports when the file runs flat. | Yes. Use absolute package imports (`from recognizer.prompts import ...`). The 7 bench scripts in `bench/hebrew-command-bench/` then import `recognizer.pipeline`, not `pipeline`. bench.py already puts the harden2 root on sys.path. | **yes**. These are our own modules, not a third-party call. | no | -- | REMOVE. This breaks the 7 bench imports, which need a one-line edit each. |
| 15 | recognizer/pipeline.py:168 | `json.loads` on the model output raises JSONDecodeError. | None (same as #4). | no | no | JSON helper | MERGEABLE |
| 16 | perception2/sam3_backend.py:131 | `self._run` -> torch forward raises `torch.cuda.OutOfMemoryError`. | No reliable one. `torch.cuda.mem_get_info()` ([docs](https://docs.pytorch.org/docs/stable/generated/torch.cuda.mem_get_info.html)) is racy against Gemma on the same GPU, and it cannot predict the forward's peak memory. But the handler only calls die(), and `install_crash_hooks()` already turns an uncaught exception in any thread into die(). | no | no | -- | REMOVE. The crash hook gives the same die. The FATAL line loses the concept name but keeps the traceback. |
| 17 | system/supervisor.py:24 | `socket.create_connection` raises OSError. | Yes. Use `socket.socket()` + `settimeout()` + `connect_ex()`. It returns an errno for a refused connection or a timeout ([connect_ex](https://docs.python.org/3/library/socket.html#socket.socket.connect_ex)); the probe confirmed 111/11. Caveat: host-name lookup can still raise gaierror, so pass numeric IPs, as the callers already do. | no | no | -- | REPLACEABLE (0 try) |
| 18 | system/supervisor.py:83 | `Popen.wait(timeout)` raises TimeoutExpired. | Yes. Use a poll loop (same as #2). | no | no | shared `stop_proc` with #2 | REPLACEABLE (0 try) |
| 19 | audio/ros2_asr.py:33 | `rclpy.shutdown()` raises RuntimeError when the context is already shut down (probe confirmed). | Yes. `rclpy.try_shutdown()` is a no-op on a context that is already shut down (Jazzy source and probe). `destroy_node` does not need a guard (#12). | no | **yes**, `except Exception` | -- | REPLACEABLE (0 try) |
| 20 | audio/phone_asr.py:55 | `json.loads` on the phone line raises JSONDecodeError. | None (same as #4). | no | no | JSON helper | MERGEABLE |
| 21 | audio/phone_asr.py:90 | `StreamReader.readline()` raises ValueError when a line exceeds the limit, and ConnectionError on a reset ([asyncio streams](https://docs.python.org/3/library/asyncio-stream.html#asyncio.StreamReader.readline)). | Partly. `read(n)` is not bound by the limit, so a hand-split buffer removes the ValueError. A reset still raises ConnectionError, so one try remains. | no | no | stream helper | MERGEABLE |
| 22 | audio/phone_asr.py:121 | `readexactly` raises IncompleteReadError, and ConnectionError on a reset. | None. The reset case always raises. | no | no | stream helper | MERGEABLE |
| 23 | audio/phone_asr.py:133 | `writer.drain()` raises ConnectionError. | None | no | no | stream helper | MERGEABLE |
| 24 | audio/phone_asr.py:156 | `start_server` bind raises OSError (the port is taken). | The handler only calls `fail()`, which reports FAILED and then dies. Replace it with a `port_open(host, port)` pre-check followed by `fail()`. The rare race after the check falls to the crash hook's die. | no | no | -- | REPLACEABLE (0 try) |
| 25 | audio/phone_asr.py:170 | `loop.call_soon_threadsafe` raises RuntimeError only on a closed loop ([docs](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe)). | Not needed. No code calls `loop.close()` on this loop, so the call cannot throw. Add `if self._loop.is_closed(): return` if a close is ever added. | no | no | -- | REMOVE |
| 26 | audio/tts_io.py:140 | `urlopen` raises HTTPError (error status) and URLError/OSError/HTTPException. | None for the connect failure (same as #1). With `http.client`, the HTTPError branch disappears, because a 4xx/5xx comes back as a status. | no | no. URLError is redundant with OSError. | HTTP helper | MERGEABLE |
| 27 | control/dji_wire.py:74 | Same as #26. | Same as #26. | no | no. URLError is redundant with OSError. | HTTP helper | MERGEABLE |
| 28 | video/camera_stream.py:78 | `executor.spin_once`. It raises `ExternalShutdownException` when the context shuts down between the `rclpy.ok()` check and the wait. It also **re-raises any exception from our own `_cb`** (Jazzy `_spin_once_impl`). | None for the shutdown race. The documented rclpy pattern catches `ExternalShutdownException` ([rclpy executors](https://docs.ros.org/en/jazzy/p/rclpy/api/execution_and_callbacks.html)). | **partly**. The broad catch swallows our own callback bugs, which should reach the crash hook. | **yes**, `except Exception`. Narrow it to `rclpy.executors.ExternalShutdownException`. | -- | UNAVOIDABLE, but narrow it |
| 29 | video/camera_stream.py:86 | `np.frombuffer(...).reshape` raises ValueError on a size mismatch ([numpy.reshape](https://numpy.org/doc/stable/reference/generated/numpy.reshape.html)). | Yes. Validate before the reshape: `msg.encoding == "bgr8"`, `msg.step >= w*3`, and `len(msg.data) >= h*msg.step`. After these exact checks, the reshape cannot fail. | no | no. TypeError cannot happen with a fixed message type. | -- | REPLACEABLE (0 try) |

## Analysis

1. The inventory holds 29 blocks, not 28. All 29 are listed above.
2. Four blocks catch exceptions from our own code: #9, #10, #14, and partly #28. #14 is the clearest breach: it is an import fallback for our own modules.
3. Six blocks use `except Exception`: #9, #10, #11, #12, #19, #28. Only #9 has a reason to stay broad.
4. Nine blocks call an API that has a non-throwing replacement, or that cannot throw at that spot: #2, #10, #11, #12, #17, #18, #19, #25, #29.
5. Three blocks exist only to call die(). The crash hook already does that: #16, #24 (via `fail()`), and #14's import path.
6. The remaining catches are true third-party throws with no non-throwing API. They cluster into four failure domains:
   - HTTP (4 blocks).
   - JSON (3 blocks).
   - Filesystem (5 blocks).
   - Phone stream socket (3 blocks).
   Each domain can have one helper with one try.
7. Four HTTP call sites catch `urllib.error.URLError` next to `OSError`. URLError is a subclass of OSError, so the catch is redundant.
8. `ros2_asr.py` spins with `threading.Thread(target=self._exec.spin)` and has no catch. So an `ExternalShutdownException` there reaches the crash hook. In `camera_stream`, the same event is only logged. The two ROS readers handle the same event in different ways. This is an open decision.
9. A single generic `guard(fn, exc_types)` helper would bring the count to 1. It only hides the tries, so it is not recommended.

## raise SystemExit (4 sites)

All four are in `__main__` self-test or smoke entry points. None are in the runtime path.

| file:line | Current | Can it be die()? |
|---|---|---|
| perception2/concept.py:117 | print problems, `raise SystemExit(1)` | Yes. Use `die("\n".join(problems))`. It gives the same exit code 1 and drops the separate print. |
| perception2/engine.py:151 | same | Yes, same change. |
| recognizer/selftest.py:119 | same | Yes, same change. |
| perception2/sam3_backend.py:168 | `raise SystemExit(_smoke())`, exit 0 or 1 | Not as written, because die() always exits 1 and would fail the success path. Use `if _smoke(): die("SAM3 backend smoke FAILED")`. The success path then ends normally with exit 0. |

Note: `raise SystemExit` is the stdlib exit mechanism (`sys.exit` raises it). It is not error handling. Converting it is for consistency, not rule compliance.

## Conclusions

- Blocks now: **29**.
- Minimum reachable without hiding the tries: **6**.
  - HTTP helper: 1.
  - JSON helper: 1.
  - Filesystem helper: 1.
  - Phone stream helper: 1.
  - rclpy spin (narrowed): 1.
  - fatal.py die cleanup: 1.

Changes to get there (all are recommendations; none are ruled):

- Add one HTTP helper that returns `(status, body)`, where status 0 means unreachable. Build it on `http.client`, so an error status is a return value and not a throw. Catch `(OSError, http.client.HTTPException)` only.
- Route `gemma/server.port_up`, `gemma/client.request`, `tts_io._post` and `dji_wire._request` through the HTTP helper. This takes 4 blocks down to 1.
- Add one `parse_json(text) -> (ok, obj)` helper that catches `json.JSONDecodeError` only.
- Use `parse_json` in `gemma/client`, `recognizer/pipeline` and `phone_asr._extract`. This takes 3 blocks down to 1.
- Add one filesystem helper module with a single OSError boundary. It exposes `append_line`, `atomic_write(path, bytes)` and `rename`.
- Route `session_log` (4 blocks) and `recognizer/trace` (1 block) through the filesystem helper. This takes 5 blocks down to 1.
- Write session JPEGs with `cv2.imencode` plus `atomic_write`, not `cv2.imwrite` plus `os.replace`.
- Add one async helper in `phone_asr`. It awaits a stream call and returns `(ok, value)` on `(ConnectionError, ValueError, asyncio.IncompleteReadError)`. Use it for readline, readexactly and drain. This takes 3 blocks down to 1.
- Add one `stop_proc(proc, grace_s)` helper built on a `poll()` loop, then kill and wait. Use it in `gemma/server.stop` and `supervisor.stop_all`. This takes 2 blocks down to 0.
- Rewrite `supervisor.port_open` with `connect_ex`. This takes 1 block down to 0.
- Delete the three teardown tries in `camera_stream._teardown`. None of those calls can throw there. This takes 3 blocks down to 0.
- Narrow `camera_stream._spin_loop` to `ExternalShutdownException`, so our own callback bugs reach the crash hook.
- Replace the reshape try in `camera_stream._cb` with the encoding, step and length checks. This takes 1 block down to 0.
- Replace `rclpy.shutdown()` with `rclpy.try_shutdown()` in `ros2_asr.shutdown` and drop the try. This takes 1 block down to 0.
- Drop the OOM try in `sam3_backend.detect`, because the crash hook dies with the traceback. This takes 1 block down to 0.
- Replace the bind try in `phone_asr._run` with a `port_open` pre-check plus `fail()`. This takes 1 block down to 0.
- Delete the `call_soon_threadsafe` try in `phone_asr.shutdown`, because the loop is never closed. This takes 1 block down to 0.
- Switch `recognizer/pipeline.py` to absolute imports and update the 7 bench scripts. This takes 1 block down to 0.
- Keep the `fatal.py` cleanup catch, and document it as the one sanctioned broad catch.
- Convert the three `raise SystemExit(1)` self-test exits to `die(...)`, and `sam3_backend`'s smoke exit to `if _smoke(): die(...)`.

Blast radius:
- Behavior changes only in log text and FATAL wording (#16, #24).
- The 7 bench scripts need an import edit (#14).
- The tests in `test/` should pass unchanged.
- The HTTP helper changes the error branch in `dji_wire` and `tts_io`, so `test_control` must re-run as the regression gate.

## Result (2026-09-24, plan step 7)

Implemented. 22 blocks in 13 files became 5: one per failure domain in `util/guarded.py`
(`http_request`, `parse_json`, `file_op`, `stream_call`) plus #9 in `system/fatal.py`. Every
REPLACEABLE and REMOVE verdict above was applied. The SAM3 out-of-memory catch and the laptop
PortAudio catch were removed too: they only called die(), and the crash hook does that with the full
traceback. The rclpy blocks were already gone (system/ros.py shutdown order).

