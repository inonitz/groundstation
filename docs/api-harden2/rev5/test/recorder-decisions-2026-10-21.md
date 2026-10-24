# The recorder: what changed, and what needs your word (2026-10-22, fourth form)

**FROZEN on 2026-10-23.** Every item below is applied and merged into `docs/api-harden2/rev5/modules/01-recorder/recorder.md`, section 2, mechanism by mechanism (RCD61). This file is the dated record of the review of 2026-10-21 and 2026-10-22. It is not edited again. recorder.md is the truth from here.

## What remains for you (2026-10-22, after the third review)

This document is the source of truth (RCD52). The headers, recorder.md, the drawings and the aggregate sync to it after your rulings.

CLOSED today: item 11, the retry without a retry queue ("I don't see any actual decision to make here"). The queues are bounded by count, 16,384 records each. A dead disk fills them in about seven minutes. Then the producers drop and count. Memory stays at the bound. Nothing calls die (TEL2). The health and the chat line show it.

APPLIED to the headers (draft 21): 4, the C buffer 16 KiB with a cut at its end. 6, the mechanism, with the names of the field. 8, everything allocated at Create. 10, the ordered shutdown. 12, the drop record under its mutex. 13, a maker returns a status. 14, the same explicit bounds in both builds. 15, one Create per process, and the test stays.

CLOSED: 1, 2, 3, 5, 7, 9, 16, T1, T3. GONE: T2.

## The words and the numbers that every item uses

A lock is a mutex. One thread holds it. Any other thread that wants it sleeps until it is released. In Python it is `threading.Lock`, a pthread mutex underneath.

The GIL is Python's one interpreter lock. It makes one bytecode atomic. `deque.append` is one bytecode. `deque.popleft` is one bytecode. `x += 1` is three bytecodes: a read, an add, a store. Another thread can run between them. Python switches threads every 5 ms by default.

Atomic means a hardware instruction, such as compare-and-swap or fetch-and-add. C has these through `stdatomic.h`. Python has them through the `atomics` package, which the frame buffer uses for the counts two processes share (FB9). Each call crosses into C through cffi, and that crossing is the cost.

Measured here on 2026-10-22, single thread, nanoseconds per operation:

| operation | ns |
|---|---|
| a counter `+= 1`, plain; unsafe when two threads do it | 32 |
| a counter `+= 1` under a Lock | 138 |
| a counter add through the atomics package | 1,545 |
| an index queue pop and push on a deque under a Lock | 255 |
| one compare-and-swap loop through the atomics package | 9,836 |

The rule that follows: a value with one writer is a plain int. A value with many writers gets a Lock, held short. The atomics package is for memory shared by two processes, the frame buffer alone.

A pass is one iteration of the writer's loop: wake, then walk every queue and the pool once (drawing 2). The next pass is the next wake, at most 5 s later.

The recorder has up to 16 recording threads. They are the main thread, the emergency thread, eight job threads, the frame source, the recognizer and the voices. One writer thread per process consumes everything and writes the file. The main thread also reads the health once per frame.

---

## 1. The index queue uses a lock. CLOSED (RCD50)

The pool manages its buffers with two index queues, the free list and the work queue. Each is a deque under its own `threading.Lock`. A pop must answer "empty" when the queue is empty, which is two bytecodes, so it needs the lock. A lock-free form would pay a compare-and-swap loop, 9,836 ns, against 255 ns for the locked pop and push. You ruled: "Lock it is".

## 2. The writer's loop returns with one arrow. CLOSED ("P3 - Good")

The writer sleeps on a `threading.Event`, wakes when it is set or after 5 s, resets it, and does one pass. A set that lands during the pass is remembered by the Event, so the next sleep ends at once. The two-arrow form skipped the reset and would spin for ever. The drawing has one return arrow into step 1.

## 3. Nothing records before Create. CLOSED ("can you record something when you don't exist yet?")

You are right: it is not an issue. Create is the app's first service, so no thread that records exists before it. A call before Create can only come from a test or a bug. It returns `RECORD_NOT_CREATED` and nothing else happens. There is no instance to count in, and nothing to decide.

## 4. The line buffer, and the size of a file. DECIDED (your words)

**In Python.** There is no buffer. The writer calls `json.dumps` on one record and gets a string of exactly that line's size. It encodes the string, writes it with `os.write`, and the string is freed. A span line is 110 bytes. An event line is about 190 bytes. The largest line ever measured was 5,849 bytes, a pass event with its boxes list.

**The file.** The file is the sum of its lines. At 40 spans a second a 40-minute flight writes about 11 MB of text. The PNGs of the same flight are about 3.7 GB. The text is 0.3 percent of the disk.

**In C.** A C build formats each line inside one fixed buffer, one per process, 16 KiB, twice the record bound. The formatter stops at the buffer's end. A line that did not fit is written as far as it got. The reader skips it as unparsable, as it skips a torn line, and the writer counts it. Nothing of this touches Python.

## 5. Destroy and Die drain everything first. APPLIED today, on your word

**What happens, in order.** Destroy, or FlushInDie from Die, sets the state to STOPPING and sets the wake flag. The writer wakes and runs its last pass. Before today the last pass drained each queue once. A record pushed after the writer passed its queue was counted as dropped. It was never written.

**Your point.** The records queued before the stop request are the ones that explain a Die. They must reach the file. A record call after the stop request is dropped and counted, by your B2. A Die during a Destroy waits for the Destroy's drain until its own deadline. And the writer cannot be out-produced. Our threads push 40 records a second. The writer writes about 130,000 lines a second, measured. So "drain until empty" ends at once.

**What the headers say now.** The last pass repeats steps 2 to 6 until every queue and both pools are empty. The deadline is the only other stop. Then it writes the die line, the time reference, the health line, and flushes. Only what the deadline cut off is popped and counted. For a Destroy that deadline is now plus the app's timeout, stored by Destroy. For a Die it is the flush cap of the Die sequence, 5 s.

**What Die does with the threads.** Die's sequence in the runtime has five steps. The hand-over, 1 s. The notify, 0.5 s. The flushes, 5 s, which is where the recorder drains. The children, 10 s. Then exit. Die does not join the recording threads; they belong to their modules and run until exit. A record call after the stop request is dropped and counted by its own thread. What the deadline cut off is counted by the writer before the final health line, so it is in the file. The only hole is a record pushed between the writer's final empty check and its STOPPED store. Its producer loaded RUNNING just before. The record stays in its queue, never written and never counted. That window is microseconds.

## 6. The buffer pool, and how a stalled frame is seen. DECIDED (the mechanism); the names of the field

**The scheme, in the field's words.** The pool is a buffer pool with a free list and a work queue. Producers fill it and one consumer drains it. The pool is a fixed set of N buffers, allocated once at Create. The free list holds the buffers nobody uses. The work queue holds the buffers that are filled and wait for the consumer. A producer takes a buffer from the free list, fills it, and puts it on the work queue. The consumer takes it from the work queue, processes it, and returns it to the free list. Two buffers is double buffering, or ping-pong. N buffers is the general case.

**Here.** The producers are the vision job threads. The fill is the copy from the shared-memory frame buffer into a pool buffer. The consumer is the writer, and the processing is the PNG encode. The writer touches nothing until a buffer is filled and on the work queue. The pool has 8 frame buffers and 24 mask buffers.

**The names, in the header.** The type is `BufferPool`, in `buffer_pool.h`, so the type itself names the scheme (your point A). Its members are `m_freeList` and `m_workQueue`, both IndexQueue, and `m_buffers`, the N buffers. Its operations are `BufferPoolTakeFree`, `BufferPoolEnqueueFilled`, `BufferPoolPeekFilled`, `BufferPoolDequeueFilled`, `BufferPoolReturnFree` and `BufferPoolOldestFilledAt`. The peek exists for item 11. A filled buffer stays at the front until its frame line is in the file. The `m_pngResult` mark on the buffer makes a retry skip the encode and keep its ok value. The recorder holds two instances, `m_framePool` and `m_maskPool`. The header's first comment states the scheme in the paragraph above. "FramePool", "slot", "free", "ready", "claim", "publish" and "release" are gone.

**A stalled frame.** A frame is a filled buffer that waits on the work queue. It stalls when the writer does not take it for 5 s past the writer's last progress. The writer stores that progress time after each buffer and at the end of each pass. The writer is stuck then: a PNG encode that does not return, a disk write that hangs, or a dead writer thread. The main thread reports it on the status row.

**What went wrong before.** The writer alone stored the oldest buffer's fill time, at the end of each pass. A writer stuck inside a pass never reaches the end. So the stored time stayed stale, and the stall was never reported.

**Now.** The pool answers the question itself. The oldest filled buffer is the front of the work queue, and every buffer carries the time it was filled. One function, `BufferPoolOldestFilledAt`, takes the work queue's lock and reads the front's fill time. It returns that time, or 0 when the queue is empty. The main thread, inside `recorder_read_health`, calls that function on each pool. It also reads the writer's last progress time, one atomic int with one writer. No stall field is shared, and nobody outside the pool touches its queue or its lock.
```python
class BufferPool:
    def oldest_filled_at(self):
        """The fill time of the oldest buffer on the work queue, or 0 when it is empty."""
        with self._work_queue_lock:
            if not self._work_queue:
                return 0
            return self._buffers[self._work_queue[0]].filled_at
```

## 7. Every thread counts its own dropped frames. CLOSED (RCD43)

A job thread notes the drop in its own drop record, under that record's mutex (item 12). The writer sums the drop records into the health counters at the end of each pass.

## 8. Everything is allocated at Create. DECIDED (your words)

**What you said.** No lazy initialization. Preallocate.

**What the headers will say.** Create makes the thread table of 16 entries. Each entry has its name, its counters, its drop lock and its queue. In C that is 16 queues of about 1 MiB, allocated at Create. A failure there makes Create return false, and the app dies at start, with the reason. No allocation happens on any thread later. A thread's first record claims the next free entry, which is an index, not an allocation. The 17th claim dies (RVW4).

**Static or bounded.** In C the memory is static after Create: nothing grows. In Python the entries and the deques exist from Create. But a deque grows by one tuple per record, and shrinks when the writer pops. So Python is bounded, not static. The bound is 16,384 records per queue. The normal fill is about 200 records between two passes, 0.1 MB. A preallocated ring of slots would make Python static too. We measured that ring at 646 ns a push, against 150 ns for the deque. So your PY3 ruling chose the deque.

## 9. Who touches the recorder's state. APPLIED

**Your question.** Why would an external component touch a thread's state. It does not. The state here is the recorder instance's state: NOT_CREATED, RUNNING, STOPPING, STOPPED. Two functions of the recorder itself change it to STOPPING. One is `recorder_destroy`, which the app calls in its close order. The other is `recorder_flush_in_die`, which Die calls as its flush step. Both go through one internal function under the state lock. The writer thread reads the state at the top of each pass and stops itself.

**So this is the terminate-and-join pattern.** `recorder_destroy` is terminate plus join. It asks the writer to stop. It waits for the "stopped" signal. Then it joins the thread. No module reaches into the writer. The same pattern holds everywhere: every module's `close()` joins its own threads, and the supervisor stops its own children.
```python
def _request_stop(self):
    with self._state_lock:
        if self._state != RUNNING:
            return False
        self._state = STOPPING
    self._wake.set()
    return True
```

**Why the lock.** Destroy ran, the writer finished, the state is STOPPED. Then Die comes. Without the lock, FlushInDie would store STOPPING over STOPPED and wait 5 s for a writer that is gone. With the lock, it sees STOPPED and returns at once.

## 10. The die reason, under an ordered shutdown. DECIDED (your words: "Good")

**What you said.** The app has no recovery code. Die terminates in order. So the destruction is synchronous and ordered, in C as in Python.

**What follows.** The stop request runs under the recorder's state lock, in both builds, as item 12 does for the drop record. Under the lock: if the state is RUNNING, store the reason, store the deadline, then store STOPPING. The writer reads the state at the top of each pass. A writer that sees STOPPING therefore sees a complete reason and a complete deadline. In C the store of STOPPING has release order and the writer's load has acquire order. That is the standard "publish the data, then raise the flag". A second stop request finds STOPPING, stores nothing, and waits for the drain.

**The one corner.** A Die that arrives during a Destroy finds STOPPING. It stores nothing and waits for the Destroy's drain until its own deadline. The file gets no die line, and the hand-over log has the reason.

## 11. A failed append, without a retry queue. CLOSED (2026-10-22)

**The mechanism, in your pseudocode.**
```
while queue is not empty:
    record = queue.front()
    line = format(record)
    if file.append(line) fails:
        counters.failed_writes += 1
        break                    # the record stays at the front; the pass ends
    queue.pop()
```
**Your first question: the records past the failed one.** When an append fails, the pass ends. It ends for every queue, not only this one. No record is popped after that point. Every record stays where it is, in its own queue, in order. Nothing is lost at that moment.

**Your second question: why the next try would succeed.** It need not. A full disk is still full. The records wait in their queues, and the writer tries again at every pass, every 5 s. After the failure the pass skips every further append, steps 5 to 8 and the fault lines. It still sums the drop records into the health counters, so the status row stays current. If the disk comes back, the backlog drains in order. If it never comes back, the queues fill in about seven minutes at 40 records a second. Then the producers drop new records and count them, and the health shows the failed writes growing. That loss is unavoidable with a dead disk. A retry queue of copies would lose it sooner, since it is smaller than the queues.

**Your third question: a pass.** One iteration of the writer's loop: wake, walk every queue and the pool once, sleep. The next pass is the next wake, at most 5 s later.

**One more fact, the order across threads.** A pass drains queue A fully, then queue B. If B's append fails, A's lines of that pass are already in the file. Lines stay in order within a thread. Across threads the reader orders by time, as it always did.

**What goes.** The retry queue of your W1 and its copies. The RetryLine type. Step 7 of the pass. The reader's rule. The failed-writes counter stays and counts attempts.

**The writer's own lines, and the buffers.** The same rule holds for them. A thread line counts as written only after its append succeeds. A filled buffer stays at the front of the work queue until its frame line is in the file. The writer peeks it, encodes the PNG once, and keeps the result on the buffer. It appends the line. Only then it dequeues the buffer and returns it to the free list. A failed append leaves it at the front; the next pass skips the encode and keeps the ok value. Inside the last pass a failed append ends that iteration, and the loop repeats after 1 s until the deadline.

## 12. The drop record under its mutex. DECIDED (your words)

**The shared data.** Each thread's entry holds a drop record. It has three counts: spans, events and frames. It has the time of the first drop and the time of the last drop. It has one mutex. Two operations exist on it, and only they touch it.

1. The producer, when its push fails because the queue is full, calls `note_drop`. It takes the mutex, stores the two times, adds one to the count, and releases the mutex. This is rare: it happens only on a drop.
2. The writer, once per pass per entry, calls `take_drop_gap`. It takes the mutex, copies the five values, and releases the mutex. Then it writes the drop line from the copy, for the count since its last drop line. Later it sums the same copy into the health counters.

Each holds the mutex for under a microsecond. No other code reads or writes those five values.

## 13. A maker returns a status. DECIDED (your pattern)

**Your pattern, in C.** A status out, a destination in, the destination unchanged on failure:
```c
bool FieldInt(RecordField* out, FieldName name, int64_t value);   /* false: out unchanged */
```
**The same idea in Python.** There are no out parameters, so a maker returns the field on success and `None` on failure. The helper that builds the record sees the `None`, stops, and returns the error code. That is common Python, and it raises nothing.

**Relevance to the Python hot path.** Small. The hot path passes names and values as plain tuples and never calls a maker. The makers exist for odd shapes. The FIELD_INVALID type goes; the status is the return value.

## 14. The same bounds, checked in both builds. DECIDED (your words)

**What you said.** Not checking a length is a failure, in Python as in C.

**What the headers will say.** Every limit lives in config, the one source, and is the same in both builds. The session path has a limit; Create returns false when the path is longer. The info JSON has a limit; Create returns false when it is longer. The folder and the name of a frame have theirs already, 64 and 32 bytes, checked in RecordFrame. A text field has the 8 KiB record bound already, enforced by the cut. The check is explicit in Python too: `len(path) <= limit`, never "the OS will refuse it".

**The reset list.** Gone. Nothing is created twice (item 15).

## 15. One Create per process. DECIDED (your words)

**A daemon.** In Unix, a daemon is a background process with no terminal. In Python's threading, a daemon thread is a thread flagged so that the interpreter does not wait for it at exit. When the main thread ends, the process exits and daemon threads are killed with it. A normal thread keeps the process alive until it finishes. The writer is a daemon thread.

**Destroy.** It waits for the writer up to its timeout. When the writer finishes in time, Destroy joins it and returns true. When it does not, Destroy returns false and leaves the state as STOPPING. The process can still exit, because the writer is a daemon thread. Destroy stores nothing.

**Create.** Once per process, at the app's start. A second call returns false. The test stays, as you said: test 22 is "a second Create returns false".

## 16. The wake flag's is-set question. CLOSED

The producer asks `is_set` before `set`, because the ask costs 23 ns and the set 332 ns. The C header now has the function for the ask. Nothing to decide.

## T1. The fault line. CLOSED (your yes, 2026-10-22)

The writer never calls a record contract, because that would be a recursive call. The writer would push into a queue it drains itself. But the writer writes lines of its own: thread lines, drop lines, health lines. The fault line is one more. At the end of each pass the writer sums the counters. For every counter or flag that changed, it writes one fault line with the time, the cause and the new value. This restores your TEL2 in full. The line kind and its keys are in record_file.h.

## T2. The retry queue. GONE

Item 11 removes the retry queue, so its depth is no question.

## T3. The blind check. Your yes received

One round of three agents, after item 11 is ruled and applied, so the round covers everything. Three green verdicts approve the module.

## The table

| ID | what | status |
|---|---|---|
| 11 | a failed append ends the pass; the record stays at the front; no retry queue | CLOSED |
| 4, 6, 8, 10, 12, 13, 14, 15 | your words, to be applied to the headers in one pass | DECIDED |
| T3 | one blind triple check after everything is applied | your yes stands |
