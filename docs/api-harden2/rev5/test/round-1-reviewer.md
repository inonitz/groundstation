# perf (rev5), round 1: the adversarial review of perf.md and perf.h (2026-10-12)

Scope: docs/api-harden2/rev5/modules/01-perf/perf.md and perf.h.
Measured numbers: Python 3.12.3 (GIL build), this machine, best of 5 runs of 200k calls.
The bench script is in the session scratchpad; each number below names what it timed.

## Sources
1. https://docs.python.org/3/library/threading.html : "Thread identifiers may be recycled when a thread exits and another thread is created." It also says thread-local data "is data whose values are thread specific."
2. https://docs.python.org/3/library/collections.html : "Deques support thread-safe, memory efficient appends and pops from either side of the deque."
3. https://peps.python.org/pep-0703/ : "A new build configuration flag, --disable-gil will be added to the configure script that will build CPython with support for running without the global interpreter lock."
4. https://docs.kernel.org/trace/ring-buffer-design.html : the ftrace ring buffer is per CPU. In producer/consumer mode "the producer will stop writing to the buffer. This will lose most recent events." When full, "we must start dropping writes (usually with some kind of warning to the user)."
5. https://lttng.org/docs/v2.13/ (section "Event record loss mode"): LTTng-UST uses per-CPU ring buffers per user or per process, in discard or overwrite mode, and counts the discarded event records. The page blocked automated reads today; this sentence is from the manual, not re-quoted.
6. https://perfetto.dev/docs/instrumentation/track-events : "Time-varying numeric data can be recorded with the TRACE_COUNTER macro." "Flows can be used to link two (or more) events (slices or instants), to mark them as related." Each thread has its own TraceWriter.
7. https://perfetto.dev/docs/reference/trace-packet-proto : "the consumer can re-establish a total order ... using the packet timestamps, after having synchronized the different clocks onto a global clock" (ClockSnapshot).
8. https://raw.githubusercontent.com/gabime/spdlog/v1.x/include/spdlog/async_logger.h : the spdlog async overflow policy is one of "block", "overrun_oldest", "discard_new". The thread pool exposes overrun_counter() and discard_counter().
9. https://lmax-exchange.github.io/disruptor/disruptor.html : "If two variables are in the same cache line, and they are written to by different threads, then they present the same problems of write contention ... 'false sharing'." Also: with a single producer "no locks or CAS operations are required."
10. https://www.usenix.org/conference/atc18/presentation/yang-stephen : NanoLog extracts the static log parts at compile time and "outputs the log in a compacted, binary format at runtime"; "8 nanoseconds in microbenchmarks."
11. https://gitea.hak8or.com/mirrors/tracy/raw/commit/c2c0f887aa6b80dcbb0e1eb33cbb19d920bc844a/manual/tracy.tex : Tracy collects events in a per-thread queue; one zone (begin plus end) costs about 15 ns.
12. https://man7.org/linux/man-pages/man2/clock_gettime.2.html : CLOCK_MONOTONIC "does not count time that the system is suspended." CLOCK_BOOTTIME "also includes any time that the system is suspended."
13. https://man7.org/linux/man-pages/man7/time_namespaces.7.html : "Time namespaces virtualize the values of two system clocks", CLOCK_MONOTONIC and CLOCK_BOOTTIME, per namespace.
14. https://design.ros2.org/articles/clock_and_time.html : "The ROSTime will report the same as SystemTime when a ROS Time Source is not active."

## Findings

**R1-1. The Python mapping cannot work: the writer thread cannot read a threading.local write index.** (critical)
- Claim: perf.md section 5 puts each ring's write index "in threading.local". A threading.local value is visible only to the thread that set it. The writer thread sees no index, so it can never drain a ring.
- Why it matters: this is the one mechanism the module exists for. The SPSC ring needs the consumer to read the producer's index (perf.md section 4).
- Evidence: measured here: a second thread reading the same threading.local attribute gets AttributeError (the test printed "INVISIBLE"). Source 1: "values are thread specific."
- Change: the ring object (slots, write index, read index) lives in the tracer's ring table. The recording thread finds its ring once and caches the ring reference in threading.local. The index lives on the ring object, which both threads can reach.

**R1-2. The payload cut at 103 bytes writes invalid JSON, and today's Gemma record is 116 bytes.** (critical)
- Claim: a cut payload ends mid-string or mid-number. The JSON line is then unparseable. The report reads lines with json.loads and stops on the first bad line.
- Why it matters: the gemma record is the plan latency, the slowest step of a turn (0.5 to 1.5 s, section 8). It would be cut on every request. The design says "about 90 bytes"; that number is wrong.
- Evidence: measured: the PERF_LLAMA_REQUEST payload with the seven listed keys and realistic values is 116 bytes. Cut to 103 bytes, json.loads raises "Unterminated string". Hebrew text is 2 bytes per letter in UTF-8. A byte cut can also split a letter, which makes the line undecodable.
- Change: never cut a payload. On overflow, store a fixed valid payload such as `"cut":116` and count it. A test writes a 200-byte payload and parses the line. Separately, size the payload from the largest real record plus margin. 104 bytes is under today's largest.

**R1-3. The tests as written contradict the ring size, so two of them cannot pass.** (high)
- Claim: test_record_from_sixteen_threads writes 10k records per thread. A ring holds 4096. The writer drains every 5 s. A Python thread writes 10k records in about 3 ms (measured: 214 to 329 ns per record). Each ring overflows and drops about 5900 records. The test expects 160k lines.
- Claim: test_record_cost_under_ten_microseconds writes 100k records on one thread. After 4096 the test times the drop path, not the write path.
- Why it matters: the owner's rule: "A test that can pass without checking anything is a bad test." These two test the wrong path or fail by design.
- Evidence: 4096 slots per ring (perf.h kPerfRingRecords); 5 s flush (R7).
- Change: the volume test writes at most 4000 records per thread, or calls PerfFlush between batches. The cost test writes 4000 records per batch and flushes between batches outside the timed region.

**R1-4. The report tests cannot stay "unchanged".** (high)
- Claim: perf.md section 6 keeps test_report_percentiles_on_known_values and test_report_slowest_frames unchanged. The report's input changes in five ways. The file name: perf.jsonl becomes perf-*.jsonl. The duration: "ms" becomes start and end. The wall time: "t" is gone. The stage names: "gemma", "sam3", "highlight_gate" are renamed or split. The field: "wait_ms" is gone.
- Why it matters: guidelines.md, "Change-impact analysis": a rewritten test means changed behavior, and it must be called out. The report's PARTS table keys on "sam3" with "wait_ms", and on "gemma". slowest_frames reads r["t"].
- Evidence: projects/integration_harden2/log/perf_report.py lines PARTS, slowest_frames, report().
- Change: state the change-impact table in perf.md. Either the writer emits a compatible line (stage name, ms, t), so the report tests stay unchanged; or the tests are rewritten and listed as rewritten.

**R1-5. Thread identity: idents are recycled, the 33rd thread is undefined, and threads have no names.** (high)
- Claim: the ring table is "a dict keyed by threading.get_ident()". CPython reuses the ident of an exited thread. A new thread then inherits the old thread's ring and its m_thread index.
- Claim: kPerfMaxThreads is 32. The behavior of the 33rd thread is not specified. A restarted worker (the supervisor restarts parts) can create new threads over a run.
- Claim: the record carries a 1-byte index only. No record maps the index to a thread name. The report cannot say "the platform worker" for a slow record.
- Why it matters: the module records from up to 16 threads (section 3). The vision pool, the voice workers and restarted listeners all share one table.
- Evidence: measured: 50 threads started and joined in turn got 1 distinct get_ident value. Source 1 states the recycling. Perfetto writes thread-name metadata per thread (source 6).
- Change: register a ring with the thread's name and native id (threading.get_native_id) on its first record. Write that table as a header line of each drain. Never reuse a ring slot while it holds undrained records. Define the 33rd thread: die() with the reason, since the thread budget is a design number.

**R1-6. PerfFlush as a second consumer, and a deadlock when the writer dies.** (high)
- Claim: PerfFlush drains "from the calling thread". The writer also drains. That is two consumers of an SPSC ring. The design says the lock is "on the file write only". If the read index moves outside that lock, two drains can emit the same records twice or skip some.
- Claim: RVW4 rules that a disk error crashes. The writer thread hits the disk error. It calls die(). die() calls PerfFlush first. PerfFlush takes the write lock. If the writer still holds it, the process hangs. A non-reentrant lock deadlocks on its own holder.
- Why it matters: die() is the crash path. A hang in its first step disables every later cleanup, including the hand-over to the RC mid-flight (section 9).
- Evidence: perf.md section 4, "Threads"; spec ledger RVW4 ("a disk error or a bug in our code crashes"); today's flush prints and continues (log/perf.py flush docstring).
- Change: the drain and the file write sit under one lock, so there is one consumer at a time. The writer releases the lock before it calls die(). die()'s flush acquires with a timeout (1 s) and gives up with a line on stderr. A test makes the write fail and checks that die() returns.

**R1-7. Destroy waits up to 5 s, and the ban on Event costs nothing here.** (medium)
- Claim: the writer "wakes every PERF_FLUSH_SECONDS" and Destroy "clears the running flag, joins". A sleeping writer sees the flag only after its sleep ends. Shutdown then blocks up to 5 s.
- Why it matters: perf is destroyed last (perf.md section 4). Every app quit and every graceful SAM3 stop pays up to 5 s.
- Evidence: PRF2's complaint was a lock on the recording path. The writer thread is not a recording thread. threading.Event.wait(timeout) is the standard interruptible sleep in Python.
- Change: the writer sleeps on an Event with the flush period as timeout. Destroy sets it, then joins. Keep the _Atomic flag only in the C language of the header.

**R1-8. A request record and its pass record cannot be joined.** (medium)
- Claim: perf.md says "The difference between the two is the socket and the queue wait" (PERF_SAM3_REQUEST minus PERF_SAM3_PASS). No shared key links a request in perf-app.jsonl to its pass in perf-sam3.jsonl. A difference of percentiles is not the percentile of the differences.
- Why it matters: the SAM3 pass runs 0.41 to 1.9 s and Gemma contention adds 0.22 s (section 8). The queue wait inside the SAM3 server is the number that shows priority contention. Today's record has it ("wait_ms"); the design loses it.
- Evidence: Perfetto links related slices across threads and processes with flows (source 6).
- Change: the app gives each SAM3 request a sequence number. Both records carry it as "req". The SAM3 server also records the queue wait (enqueue to dequeue) in PERF_SAM3_PASS. The same "req" key goes on the llama request and on E2E, which then joins to the turn.

**R1-9. The E2E start crosses clock domains that the design does not name.** (medium)
- Claim: "The F5 release arrives as a Key message with its time." The release comes from the C++ keyboard hook over ROS2. A ROS2 header stamp is ROS time, which equals system time (CLOCK_REALTIME) without a time source. The phone's transcript times come from another machine's clock. Neither is CLOCK_MONOTONIC of this machine.
- Why it matters: E2E is the emergency budget, under 1 s (section 8). Mixing a realtime stamp with a monotonic end gives a meaningless span.
- Evidence: source 14. The design's own rule says every stamp is PerfNow.
- Change: state that every start is stamped with PerfNow on receipt, in the listener thread. Record the hook-to-listener hop as unmeasured, or measure it once against the ROS stamp on the same host with CLOCK_REALTIME on both ends.

**R1-10. The wall-clock pair, suspend and the container namespace.** (medium)
- Claim: the slowest-frames list prints a time of day (V1). Today each record carries "t". The design writes "the wall-clock of the session start" in meta.json, from the session log, at a different instant. Without a (monotonic, realtime) pair taken together, the conversion is off by the gap between the two reads.
- Claim: CLOCK_MONOTONIC stops during suspend. A span across a laptop lid-close is undercounted and looks normal.
- Claim: two processes share CLOCK_MONOTONIC only inside one time namespace. If the SAM3 server ever runs in another container with a time namespace, the merge is wrong without any error.
- Evidence: sources 12 and 13. Perfetto writes a ClockSnapshot of all clocks into each trace for exactly this merge (source 7).
- Change: each perf file starts with one header line: process, pid, CLOCK_MONOTONIC, CLOCK_REALTIME and CLOCK_BOOTTIME read back to back. The report converts with it, and flags a file whose BOOTTIME minus MONOTONIC differs from the other file's (a suspend, or another namespace).

**R1-11. Drops are counted only at close, so a crash loses the count and the report never sees it.** (medium)
- Claim: "The writer prints the drop count at close." A crash or a kill never reaches close. A drop is also invisible in the percentile table, which then reads as complete.
- Why it matters: C.1 says "Record everything". A silent gap in a percentile table is a wrong number.
- Evidence: ftrace and LTTng both report lost events in the trace stream itself (sources 4, 5). spdlog keeps a discard counter that callers read during the run (source 8).
- Change: keep "drop the new record" (it matches ftrace producer/consumer mode and spdlog discard_new; source 4 and 8). The writer emits one line per drain per ring with dropped records since the last drain. The report prints the total above the table.

**R1-12. fsync is not specified, so the 5 s crash promise depends on the kind of crash.** (medium)
- Claim: the design says the writer "appends them to the file with one write". It does not say fsync. Without fsync, a process crash keeps the data, but a power loss or a kernel panic loses everything in the page cache.
- Why it matters: the project's hardware notes record a laptop that cold-reboots under peak draw. Today's append_line fsyncs on every flush (util/guarded.py).
- Evidence: projects/integration_harden2/util/guarded.py, append_line: "Append one text line and fsync it."
- Change: state one fsync per drain. At one drain per 5 s, the cost is one fsync per 5 s.

**R1-13. The 128-byte record copies a C layout into Python and costs more than it saves.** (medium)
- Claim: in Python, struct.pack_into into a bytearray costs more than storing a tuple, and the writer must unpack and decode each record. A Python str is immutable, so storing a reference is already a copy that the caller cannot change.
- Why it matters: the force is "microseconds, with no lock". Both shapes meet it. The bytearray adds code and a payload size limit that causes R1-2.
- Evidence (measured, ns per record, two PerfNow calls included): a tuple into a preallocated list ring, 214. struct.pack_into into a bytearray ring, 329. Writer, 500 records: tuples to JSON 0.09 ms; bytearray unpack plus decode plus JSON 0.29 ms.
- Change: a ring is a preallocated list of 4096 slots holding (stage, start, end, payload) tuples. The 128-byte layout stays in perf.h as the C design.

**R1-14. The record cost is dominated by the caller's payload, not by the lock the design removes.** (medium; questions the cost of PRF2, does not overturn it)
- Claim: today's record (dict, update, uncontended lock, append) costs 957 ns. The proposed ring costs 214 to 329 ns. Building the payload costs more than either: an f-string with three floats 437 ns; json.dumps of a dict 2368 ns.
- Why it matters: at 30 frames per second, today's record costs about 30 us per second, under 0.01 % of the frame budget. The design's "2 to 4 us" estimate is unmeasured; the dominant term is the caller's formatting, which the design does not specify.
- Evidence: measured numbers above. NanoLog reaches 8 ns by moving formatting out of the hot path entirely (source 10). Tracy reaches about 15 ns per zone the same way (source 11).
- Change: the caller passes a pre-built f-string or a tuple of numbers. perf.md forbids json.dumps on a record site. PERF_NONE is checked before the payload is built at the frame site, since Python evaluates arguments before the call.

**R1-15. The free-threaded build breaks the "a single int store is atomic under the GIL" argument.** (medium)
- Claim: the SPSC correctness in Python rests on the GIL ordering every store. Python 3.13 and later ship a build without the GIL (PEP 703). There, the writer may see the new index before the slot's store.
- Why it matters: the claim "no lock, no compare-and-swap" holds only for the GIL build. Nothing in the design pins that build.
- Evidence: source 3. Measured here: Python 3.12.3, GIL build.
- Change: PerfCreate checks sys._is_gil_enabled() when it exists, and dies with the reason when the GIL is off. Or use a collections.deque per thread, whose append and popleft are documented thread-safe (source 2) and stay correct without the GIL.

**R1-16. The gauge is a counter sample forced into a span record.** (medium)
- Claim: PERF_GAUGE has start equal to end. The report's percentile table would show a "gauge" row of 0 ms values. Seven unrelated numbers share one record.
- Claim: the sampler thread reads app counters from outside the main thread. Section 3 says only the main thread owns app state.
- Why it matters: the pre-mortem asked for queue depths next to the timings. The shape decides whether the report can plot them.
- Evidence: Perfetto keeps counters as their own track type (TRACE_COUNTER), separate from slices (source 6).
- Change: a counter record kind with one name and one value. The main thread samples once every 30 frames, since it already reads the status rows each frame and owns the queues. pynvml costs 0.018 ms per sample (config/constants.py comment). No new thread is needed. The report gets its own counter section.

**R1-17. The stage list loses data that today records, and misses the core hand-off.** (medium)
- Claim: the "imports" startup record is gone. The SAM3 lock or queue wait is gone (R1-8).
- Claim: no stage times the message queue: the enqueue time to the main thread's drain. Every Decision, PlatformReply and VisionResult passes through it (section 4).
- Claim: no stage names the emergency path. The emergency thread sends its own POST (section 3). It is not clear whether PERF_E2E covers it.
- Claim: the startup stage does not say what happens on a supervisor restart.
- Why it matters: the emergency budget is under 1 s, and the message queue sits on every path to it.
- Evidence: perf.md section 5 table; 01-system-architecture.md sections 3 and 4.
- Change: add PERF_EMERGENCY (stop pressed to the POST reply) and a queue-latency stage, or a "queued" field on PERF_E2E. Add a "restart" key to PERF_STARTUP. Keep "imports" as a row value.

**R1-18. The header exposes the ring, and the ring's indexes share one cache line.** (low)
- Claim: PerfTracer is opaque, yet PerfRing is in the public header. A caller can then reach the ring. The house rule is "opaque only for OS resources with no app state" (TEL1, PRF2), and the ring is the tracer's internal state.
- Claim: m_write (producer), m_read (consumer) and m_dropped sit in one 64-byte line. This is false sharing in the C design.
- Why it matters: the header is the contract the owner approves. At 100 records per second the false sharing costs nothing measurable; the exposure is the real issue.
- Evidence: source 9 on false sharing and the single-writer principle.
- Change: move PerfRing and PerfEvent out of perf.h. If they stay, pad m_write and m_read to separate cache lines.

**R1-19. Departures from PRF2 and from section 11 that the document does not call out.** (low)
- Claim: PRF2 gives PerfOpen(sessionDir, maxEvents). The header has PerfCreate(sessionDir, processName) with no capacity. The ring size becomes a fixed constant, while R7 asked for the flush period in config.
- Claim: 01-system-architecture.md section 11 says "Perf is reached through one entry point per process, not a handle per Create". perf.md hands a tracer pointer to each module's constructor.
- Why it matters: a ruling is a fixed constraint. A departure needs the owner's word.
- Evidence: the ledger row PRF2; section 11 of the design document.
- Change: list both as open points in perf.md section 5. Put the ring size in config next to PERF_FLUSH_SECONDS.

**R1-20. The test list misses the failure paths.** (low)
- Claim: no test covers a recycled thread ident, a 33rd thread, a payload over the limit parsed back, a write failure that calls die(), the clock header line, the in-stream drop line, or the build without the GIL.
- Why it matters: the owner's rule: "Mutation-check new logic." Each item above is a branch with no test.
- Change: add one test per item. Name each after the behavior, like the existing list.

## Questions for the manager agent
1. R1-14 questions the cost of PRF2: the measured saving is about 0.7 us per record. Does the owner want this number before the build, or is PRF2's shape final regardless?
2. R1-19: is section 11's "one entry point per process" a module-level global, or the pointer in each constructor? The two designs differ in every module's constructor.
3. R1-2: may the payload stop being caller-built JSON text (a stage schema with numbers), or is "payloadJson" in PRF2 fixed?
4. R1-15: will harden2 ever run on a Python build without the GIL? If no, the guard in PerfCreate is enough.
5. R1-16: is the gauge wanted at all (open point 2 of perf.md)? If yes, may it be a counter kind of its own rather than a stage?
6. R1-17: does PERF_E2E cover the emergency stop, or does the emergency thread need its own stage against the 1 s budget?
7. R1-9: is the hook-to-listener hop (ROS2) part of the E2E budget the owner means, and must it be measured?
