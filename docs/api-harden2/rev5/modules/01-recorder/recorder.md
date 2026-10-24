# The recorder: spans, events and frames of one process, to disk (rev5 module 1; folds perf and telemetry)

The owner's framing, 2026-10-18: "Both telemetry and perf need to write to some file, to log
whatever they're documenting. Albeit with different requirements, yes." And: "WE ARE LOOKING TO
MEASURE PERFORMANCE ON SPECIFIC OPERATIONS AND(!) RECORD TELEMETRY!" The names are his:
"Call it RecorderCreate() and destroy(), recordSpan(), recordEvent(), recordFrame(), and so on."
The files (the owner, 2026-10-18, RCD5: "If something is logically separated then put it in another file"; RCD21: one header per actor): in 00-util, `fixed_text.h`, `common_names.h`, `monotonic_clock.h`, `frame_types.h` (FrameSize, PixelFormat, FrameView), `index_queue.h` (a bounded FIFO of indexes under one lock), `spsc_record_queue.h` (one producer, one consumer, bounded, drop-new; in C a ring of record slots plus a byte area; in Python a deque of tuples, PY3). In 01-recorder, the public contracts: `recorder.h` (the lifetime, the health), `record_field.h` (typed fields with literal names, the result code, the 8 KiB bound, the cut field), `record_span.h`, `record_event.h`, `record_frame.h` (one contract each), `record_file.h` (the file: every line kind and every key as a named constant, one home for the writer and the readers). The actors: `recording_thread.h` (the producers: a thread's queue and its thread-local producer), `image_buffer_pool.h` (a buffer pool with a free list and a work queue; the job threads fill image buffers, the writer empties them), `record_writer.h` (the one consumer and the file), `recorder_internal.h` (the one instance, its state, the counters). Sixteen headers, all in `recorder_aggregate_for_review.md`. The two approved documents stay the record of their rounds. Since 2026-10-22 this document is the source of truth of the design (RCD61). **APPROVED by the owner on 2026-10-24 (RCD75), from section 2 and the six drawings.** The decision document of 2026-10-21 is merged into section 2 and frozen as a dated record. The history of the rounds moved to test/recorder-history-2026-10-24.md on 2026-10-24 (RCD72). Perf and telemetry folded in on 2026-10-24 (section 8, RCD77). This
document holds the design as it stands after every ruling (the dated record lists each change against the two approved contracts). Where a number or a measurement
is needed, it points at the two approved documents instead of copying them.

## 1. The job, in one sentence
The recorder writes a process's spans, events and frames to the session folder, from any
thread, without ever making a caller wait.

## 2. The mechanisms, each in four steps (the truth of the design since 2026-10-22, RCD61)
This section is the design in the field's words. Each mechanism comes in four steps. First the scheme, in the field's established words. Second our case: the threads, the objects, the rates. Third the Python form, the build, as code. Fourth the C form, only where it differs. Then what went wrong before, and what happens now. The code carries its own context: section 2.0 declares every object once, and every snippet uses those names. The prose after a snippet holds only what the code cannot show: the edge cases, the numbers, the why. The headers are one rendering of this section. The drawings in `recorder.html` are another. Where a header and this section disagree, this section is right, and the header is fixed.

### 2.0 The words, the numbers, and the objects of the Python build
A lock is a mutex. One thread holds it. Any other thread that wants it sleeps until it is released. In Python it is `threading.Lock`, a pthread mutex underneath.

The GIL is Python's one interpreter lock. It makes one bytecode atomic. `deque.append` is one bytecode. `deque.popleft` is one bytecode. `x += 1` is three bytecodes: a read, an add, a store. Another thread can run between them. Python switches threads every 5 ms by default.

Atomic means a hardware instruction, such as compare-and-swap or fetch-and-add. C has these through `stdatomic.h`. Python has them through the `atomics` package. The frame buffer uses that package for the counts two processes share (FB9). Each call crosses into C through cffi, and that crossing is the cost.

Measured here on 2026-10-22, single thread, nanoseconds per operation:

| operation | ns |
|---|---|
| a counter `+= 1`, plain; unsafe when two threads do it | 32 |
| a counter `+= 1` under a Lock | 138 |
| a counter add through the atomics package | 1,545 |
| an index queue pop and push on a deque under a Lock | 255 |
| one compare-and-swap loop through the atomics package | 9,836 |
| a span push: one tuple into a deque, with two clock reads | 150 |
| `Event.is_set` | 23 |
| `Event.set` | 332 |
| a wake of the sleeping writer, a futex call | 1,800 |
| one line formatted by the writer | 2,900 |
| one line written by the writer | 1,400 |

The rule that follows: a value with one writer is a plain int. A value with many writers gets a Lock, held short. The atomics package is for memory shared by two processes, the frame buffer alone.

A pass is one iteration of the writer's loop: wake, then walk every queue and both pools once. The next pass is the next wake, at most 5 s later.

The recorder has up to 16 recording threads. They are the main thread, the emergency thread, eight job threads, the frame source, the recognizer and the voices. One writer thread per process consumes everything and writes the file. The main thread also reads the health once per frame. A 25,000-line burst took the writer 185 ms, about 130,000 lines a second. Our threads push about 40 records a second. So the writer is never out-produced.

**The objects of the Python build, declared once.** Every snippet below uses these names. Each class is the Python form of the C struct named after it. The C member is the same name with its `m_` prefix. Members and functions are camelCase (the owner, 2026-10-24); the standard library keeps its own spelling. The constants come from `config/`, the one source of every value.
```python
# recorder.py: the constants, from config/; the C name after each
RECORDING_THREADS_MAX = 16          # kRecordingThreadsMax
RECORD_QUEUE_RECORDS = 16384        # kRecordQueueRecords
RECORD_QUEUE_WATERMARK = 8192       # kRecordQueueWatermark: a push past it wakes the writer
RECORD_MAX_CALLER_FIELDS = 31       # kRecordMaxCallerFields
RECORD_MAX_RECORD_BYTES = 8192      # kRecordMaxRecordBytes
FRAME_POOL_BUFFERS = 8              # kFramePoolBuffers
MASK_POOL_BUFFERS = 24              # kMaskPoolBuffers: 8 frames times 3 masks a pass
WRITER_WAKE_EVERY_NS = 5_000_000_000      # WRITER_WAKE_EVERY_NS
WRITER_FLUSH_TO_DISK_EVERY_NS = 5_000_000_000   # WRITER_FLUSH_TO_DISK_EVERY_NS
WRITER_STALL_NS = 5_000_000_000     # WRITER_STALL_NS
SESSION_DIR_MAX = 192               # kRecorderSessionDirMax
PROCESS_NAME_MAX = 31               # kRecorderProcessNameMax
INFO_JSON_MAX = 8192                # kRecorderInfoJsonMax

MonotonicNs = int                   # time.monotonic_ns()
ThreadIdx = int                     # an index into the producers table; "t" in the file
FieldNames = tuple[str, ...]        # string literals, in the caller's order
FieldValues = tuple                 # one value per name: int, float, bool or str


class RecorderState(Enum):
    NOT_CREATED = 0
    RUNNING = 1
    STOPPING = 2
    STOPPED = 3


class RecordResult(Enum):
    OK = 0
    DROPPED = 1
    INVALID_ARG = 2                 # counted as a drop
    NO_FRAME_POOLS = 3              # a caller's bug: no entry to count in
    NOT_CREATED = 4                 # a caller's bug: no instance to count in
    NOT_REGISTERED = 5              # a caller's bug: the thread never registered


class PngOnDiskStatus(Enum):        # the writer's one write of the PNG file to the disk
    WRITE_PENDING = 0
    WRITTEN = 1
    WRITE_FAILED = 2
    NAME_CLASH = 3


class QueuedKind(Enum):             # what a producer puts into its queue for the writer
    SPAN = 1
    EVENT = 2
    THREAD_NAME = 3                 # pushed once, at registration: the file's thread line
    DROP_LINE = 4                   # pushed when a run of drops ends: the file's drop line, built by the thread


SpanRecord = tuple[QueuedKind, SpanStage, MonotonicNs, MonotonicNs, FieldNames, FieldValues]
EventRecord = tuple[QueuedKind, str, MonotonicNs, FieldNames, FieldValues]
ThreadNameRecord = tuple[QueuedKind, str]                         # the thread's name
QueuedRecord = SpanRecord | EventRecord | ThreadNameRecord | DropLine   # tuples, 150 ns a push; the drop line is a small object


class Statistics:                   # util/statistics.py: named integer counters, one per field
    def __add__(self, other): ...   # field by field
    def __sub__(self, other): ...
    def __iadd__(self, other): ...  # in place
    def __bool__(self): ...         # True when any counter is non-zero
    def copy(self): ...


class RecordingThreadStatistics(Statistics):   # what one producer did, since Create
    spansQueued: int                # all eight are the thread's own: plain in Python, relaxed atomic in C
    eventsQueued: int
    framesQueued: int               # into the frame pool
    masksQueued: int                # into the mask pool
    spansDropped: int
    eventsDropped: int
    framesDropped: int
    masksDropped: int


ONE_SPAN_DROPPED = RecordingThreadStatistics(spansDropped=1)       # the units a drop adds
ONE_EVENT_DROPPED = RecordingThreadStatistics(eventsDropped=1)
ONE_FRAME_DROPPED = RecordingThreadStatistics(framesDropped=1)
ONE_MASK_DROPPED = RecordingThreadStatistics(masksDropped=1)


class DropLine:                     # the file's drop line, built by the thread while it drops
    kind: QueuedKind                # DROP_LINE
    dropped: RecordingThreadStatistics    # only the four dropped counters are non-zero
    firstDropTimestamp: MonotonicNs       # "from": where the hole in the records starts
    latestDropTimestamp: MonotonicNs      # "to": where it ends so far


class RecordingThread:              # one PRODUCER: a registered thread's entry in the producers table
    threadIndex: ThreadIdx          # the name travels as the first queued record, not here
    recordsToWriter: deque[QueuedRecord]   # no maxlen: pushRecord checks the length and drops the newest
    statistics: RecordingThreadStatistics
    pendingDropLine: DropLine | None   # the hole being counted; queued before the next record that
                                       # succeeds, as perf's PERF_RECORD_LOST is
    dropLineLock: threading.Lock    # the writer takes a line still pending at the last pass (2.7)


class ProducerSlot(threading.local):   # one slot per thread; private to producerOfThisThread() and
    producer: RecordingThread | None = None   # bindProducerToThisThread() below


class IndexQueue:                   # index_queue.h, util: a deque of ints under one Lock
    def push(self, index) -> bool: ...        # False: full
    def pop(self) -> int | None: ...          # the oldest, removed; None: empty
    def front(self) -> int | None: ...        # the oldest, not removed; None: empty


class ImageBuffer:                  # image_buffer_pool.h: one frame or one mask; section 2.4
    pixels: numpy.ndarray           # a view into the pool's pixel block
    frameCaptureTimestamp: MonotonicNs    # when the frame source wrote the frame; a mask carries its frame's
    frameCopiedInTimestamp: MonotonicNs   # when the pixels were copied in from the shared slot
    folderName: str                 # one or two names under the session folder, "perception/0004-highlight"
    fileName: str                   # the PNG's name without its extension, "000012"
    status: PngOnDiskStatus         # WRITE_PENDING until the writer's one write


class ImageBufferPool:              # an object pool with a free list, plus a work queue
    pixelBlock: numpy.ndarray       # (count, height, width, channels): one allocation at Create
    buffers: list[ImageBuffer]      # buffers[i].pixels is pixelBlock[i]
    freeList: IndexQueue
    workQueue: IndexQueue           # filled buffers, oldest first


class RecordFile:                   # record_writer.h
    fileDescriptor: int             # opened with O_CREAT | O_EXCL | O_APPEND | O_CLOEXEC
    filePath: str                   # <sessionDir>/record-<process>-<pid>.jsonl
    def appendLine(self, line: bytes) -> bool: ...    # False: failed; truncated to the line's start
    def flushToDisk(self): ...                        # os.fsync
    def close(self): ...


class RecordWriterStatistics(Statistics):      # what the one consumer did, since Create
    linesWritten: int
    bytesWritten: int
    failedAppends: int              # appends to the record file that failed
    linesCut: int                   # C only: lines longer than the line buffer
    pngsWritten: int
    pngFailures: int
    pngNameClashes: int
    flushes: int
    recordsCutOffAtDeadline: int    # the last pass: records still queued when the drain deadline passed
    imagesCutOffAtDeadline: int     # the same, for filled images


class RecordWriter:                 # the one CONSUMER of every producer's queue and both pools
    thread: threading.Thread        # daemon=True
    wakeFlag: threading.Event
    stoppedFlag: threading.Event    # set after the last pass
    drainDeadline: MonotonicNs      # the stop request gives the writer until this time to write what is
                                    # queued; what remains then is counted as dropped and the writer stops.
                                    # Destroy: now plus its timeout; Die: its 5 s flush cap (2.6, 2.7)
    dieReason: str                  # "" unless the stop request came from Die
    statistics: RecordWriterStatistics
    lastFlushTimestamp: MonotonicNs # the 5 s step: free space, time reference, health line, flush


class RecorderHealth:               # recorder.h: the status row's data, the aggregate; no lock, eventually consistent
    producersTotal: RecordingThreadStatistics   # the sum over the producers table, at the end of each pass
    consumer: RecordWriterStatistics            # a copy of the writer's
    lastAppendFailed: bool
    freeSpaceUnderReserve: bool     # under 5 minutes of frames on the disk: frames are refused
    freeSpaceGiB: float
    writerStalled: bool             # set by readHealth on the returned copy: no filled image taken for 5 s


class Recorder:                     # recorder_internal.h: the one instance; all made at Create (2.9)
    producers: list[RecordingThread]      # RECORDING_THREADS_MAX entries; the writer walks all of them
    nextProducerIndex: itertools.count    # the entry allocator: atomic under the GIL, a fetch-and-add in C
    threadLocal: ProducerSlot
    consumer: RecordWriter
    expectedFrameSize: FrameSize    # every recorded frame must match it
    framePool: ImageBufferPool | None     # BGR24; None in a process created without frames
    maskPool: ImageBufferPool | None      # GRAY8
    outputFile: RecordFile
    health: RecorderHealth          # the writer stores, the main thread reads; each field atomic, the set not
    state: RecorderState
    stateLock: threading.Lock       # the stop request (2.6) alone
    processName: str
    sessionDir: str


recorder = Recorder()               # module-level; state NOT_CREATED until create
```

### 2.1 A span or an event: the push, on the calling thread (drawing 1)
**The scheme, in the field's words.** A single-producer single-consumer queue is a bounded first-in first-out queue. One thread pushes and one thread pops. Each index has one writer, so no lock is needed. The producer stores the record, then publishes its index. The consumer reads the oldest record, uses it, then removes it. A full queue drops the new record and counts the loss. That policy is drop-new. Profilers in the field use one such queue per thread: NanoLog, Tracy, LTTng, Perfetto. The hot path stores numbers; the consumer makes the text later. Everything the file must know about the thread travels in that stream, in order. That is its name, once, and the count of each hole where records were dropped.

**Here.** A thread registers at its start and becomes one producer. It gets one entry of the producers table, with its own queue of 16,384 records (RCD35) and its own statistics. Registration pushes the thread's name as the first record. The writer is the one consumer of every queue. A span is a stage, two clock stamps and typed fields. An event is a topic, one stamp and typed fields. A field is a name and a value; the names are string literals (K1). A record is one tuple in Python. All of this code is `recorder.py`; nothing outside it touches these objects.

**The drop line, and why the thread writes it.** A reader of the file sees records at 10.0 s and at 10.7 s, and nothing between. Were there none, or were they lost? The health totals say how many were lost in the whole run, not where. So the thread writes the answer at the hole itself. While it drops, it counts into a pending drop line. That line holds the counts by kind and the first and latest drop time. At its next successful push it queues that line first, then the record. The writer only formats it. The file then reads: 412 spans dropped, from 10.0 to 10.7, exactly where the hole is. This is the Linux perf ring buffer's rule, PERF_RECORD_LOST, with ULog's duration added.

**The Python form.**
```python
def registerThread(threadName):                           # at the thread's start, once
    if producerOfThisThread() is not None:
        die("a thread registered twice")                  # a bug of ours

    threadIndex = next(recorder.nextProducerIndex)        # atomic: one call into C, no lock
    if threadIndex >= RECORDING_THREADS_MAX:
        die("a 17th recording thread")                    # RVW4: a bug of ours

    producer = recorder.producers[threadIndex]
    bindProducerToThisThread(producer)
    producer.recordsToWriter.append((QueuedKind.THREAD_NAME, threadName))   # the queue is empty here


def unregisterThread():                                   # at the thread's end
    bindProducerToThisThread(None)                        # the writer still drains the queue


def producerOfThisThread():                               # None until registerThread
    return recorder.threadLocal.producer


def bindProducerToThisThread(producer):
    recorder.threadLocal.producer = producer


def recordSpan(stage, start, end, names, values):         # recordEvent: the same, with a topic
    producer = producerOfThisThread()
    refusal = refusalIfNotRecording(producer, ONE_SPAN_DROPPED)
    if refusal is not None:
        return refusal

    if len(names) > RECORD_MAX_CALLER_FIELDS:
        return countAndRefuse(producer, ONE_SPAN_DROPPED, RecordResult.INVALID_ARG)

    names, values = cutTextsToRecordBound(names, values)
    record = (QueuedKind.SPAN, stage, start, end, names, values)
    if not pushRecord(producer, record, ONE_SPAN_DROPPED):
        return RecordResult.DROPPED

    producer.statistics.spansQueued += 1                  # the thread's own counter
    return RecordResult.OK


def refusalIfNotRecording(producer, dropUnit):            # None when the call may record
    state = recorder.state                                # loaded once per call
    if state == RecorderState.NOT_CREATED:
        return RecordResult.NOT_CREATED                   # no instance: counted nowhere
    if producer is None:
        return RecordResult.NOT_REGISTERED                # no entry: counted nowhere
    if state != RecorderState.RUNNING:                    # STOPPING or STOPPED
        return countAndRefuse(producer, dropUnit, RecordResult.DROPPED)
    return None


def countAndRefuse(producer, dropUnit, result):
    countDroppedRecord(producer, dropUnit)
    return result


def pushRecord(producer, record, dropUnit):               # perf's rule: the LOST record goes first
    queue = producer.recordsToWriter
    before = len(queue)
    slotsNeeded = 2 if producer.pendingDropLine else 1

    if before + slotsNeeded > RECORD_QUEUE_RECORDS:
        countDroppedRecord(producer, dropUnit)
        return False

    emitPendingDropLine(producer)
    queue.append(record)
    wakeWriterIfHalfFull(before)                          # section 2.3
    return True


def countDroppedRecord(producer, dropUnit):               # the thread, on a refusal of any kind
    producer.statistics += dropUnit                       # the thread's own counters

    now = monotonicNow()
    with producer.dropLineLock:
        line = producer.pendingDropLine
        if line is None:
            line = DropLine(QueuedKind.DROP_LINE, RecordingThreadStatistics(), now, now)
            producer.pendingDropLine = line
        line.dropped += dropUnit
        line.latestDropTimestamp = now


def emitPendingDropLine(producer):                        # after a success, when a slot is free
    if len(producer.recordsToWriter) >= RECORD_QUEUE_RECORDS:
        return                                            # no slot: the hole stays open

    line = takePendingDropLine(producer)
    if line is not None:
        producer.recordsToWriter.append(line)


def takePendingDropLine(producer):                        # None when no hole is open
    with producer.dropLineLock:
        line = producer.pendingDropLine
        producer.pendingDropLine = None
        return line
```

**What the code does not show.**
- The cut. A record is at most 8 KiB (RCD36). A text past the remainder is cut at a UTF-8 character start. The record then gains the field "cut", the bytes lost (RCD37). A record is never refused for its text. The largest record measured is 5,849 bytes.
- The length check and the append are one bytecode each, and only this thread appends. So nobody grows the queue between them; the writer only shrinks it.
- A hole closes at the first success of any kind, a frame included. The drop line needs its own slot. A queue with one free slot drops the record and keeps the hole open. A hole still open at the last pass is written from the pending line (2.7).
- `INVALID_ARG` is counted as a drop. `NOT_CREATED` and `NOT_REGISTERED` are not: there is no entry to count in.
- `nextProducerIndex` only grows. Entries are never reused (RCD71), so a thread index is unique for the process. The writer walks all 16 entries every pass; an unregistered one has an empty queue and zero statistics.
- The cost: 150 ns a push with the two clock reads (PY3), plus one plain increment of 32 ns.

**The C form.** The queue is a ring of record slots plus a byte area (`spsc_record_queue.h`). The head is the producer's and the tail the consumer's, each on its own cache line. A push stores the bytes and the slot, then the head with release order. The consumer loads the head with acquire order, so it sees whole records. The thread-local pointer is `_Thread_local RecordingThread* tls_producerOfThisThread`, filled by `RecorderRegisterThread`. The registration is one `atomic_fetch_add` on `m_nextProducerIndex`; no lock, no ordering, since the writer needs nothing from the entry. The statistics are structs of `RecordCount`; `StatisticsAdd` and `StatisticsSubtract` walk them as arrays. The counters are incremented with relaxed atomic builtins and copied with relaxed loads. So the writer's copy needs no lock. Only the pending drop line sits under `m_dropLineLock`. A maker is `bool FieldInt(RecordField* out, FieldName name, int64_t value)`. On false the destination is unchanged and the helper stops, as in Python. The field name travels as a pointer to the literal.

**What went wrong, and what happens now.** The R4 design had a byte ring with reserve and commit in Python too. It measured 646 ns a push against 150 ns for the deque. So the owner chose the deque (PY3). The C header keeps the ring as the embedded form. A `FIELD_INVALID` field type existed for a maker's bad value. It is gone; the maker's status is its return value (item 13). Three faults followed, all rejected by the owner on 2026-10-24 (RCD65 to RCD68). A thread got its entry at its first record, through an uninitialized thread-local object. A dropped-records type stood apart from everything else the thread counts. Two runs of drops inside one pass were merged into one drop line. Now a thread registers explicitly and counts everything in one statistics object. Every hole reaches the file as its own drop line.

### 2.2 The writer's pass: every queue, both pools, the file (drawing 2)
**The scheme, in the field's words.** One consumer thread drains many producer queues in a loop. Each iteration is a pass. The consumer formats the records into text, off the hot path, and appends to one file. It wakes on a signal or on a timer. A write that fails leaves the record where it is, so the file keeps its order. The consumer retries at the next pass. This is the usual writer thread of a logger with per-thread queues.

**Here.** The writer is the one consumer of every producer's queue and both pools, and the one producer of the file. One pass has seven steps, in the order of the code below.

**The Python form.**
```python
class RecordWriter:
    def run(self):                                            # the thread's whole loop
        while True:
            self.wakeFlag.wait(WRITER_WAKE_EVERY_NS / 1e9)    # step 1: sleep, 5 s at most
            self.wakeFlag.clear()
            if recorder.state == RecorderState.STOPPING:
                self.lastPass()                               # section 2.7
                return
            self.onePass()

    def onePass(self):
        producers = recorder.producers                                  # step 2: all 16 entries
        appendsOk = True
        for producer in producers:                                      # step 3: every queue
            appendsOk = appendsOk and self.drainQueue(producer)
        copies = [self.copyStatistics(producer) for producer in producers]   # step 4: for the health
        appendsOk = appendsOk and self.drainPools()                     # step 5: section 2.4
        if appendsOk:
            self.flushIfDue()                                           # step 6, every 5 s
        self.endOfPass(copies, appendsOk)                               # step 7: section 2.5

    def drainQueue(self, producer):
        queue = producer.recordsToWriter
        while queue:
            record = queue[0]                                 # the front, not removed
            line = formatRecord(producer.threadIndex, record) # json.dumps; by the record's kind
            if not self.append(line):
                return False                                  # the record stays at the front
            queue.popleft()
        return True

    def copyStatistics(self, producer):
        return producer.statistics.copy()                 # one writer; relaxed loads in C

    def append(self, line):
        data = line.encode()
        ok = recorder.outputFile.appendLine(data)
        if ok:
            self.statistics.linesWritten += 1
            self.statistics.bytesWritten += len(data)
        else:
            self.statistics.failedAppends += 1
        recorder.health.lastAppendFailed = not ok
        return ok

    def flushIfDue(self):
        now = monotonicNow()
        if now - self.lastFlushTimestamp < WRITER_FLUSH_TO_DISK_EVERY_NS:
            return
        self.checkFreeSpace()                                 # the reserve flag, the free GiB
        self.append(timeReferenceLine())
        self.append(healthLine(recorder.health))
        recorder.outputFile.flushToDisk()
        self.statistics.flushes += 1
        self.lastFlushTimestamp = now
```

**What the code does not show.**
- `drainQueue` is the owner's pseudocode of item 11, line for line. A failed append breaks with the record at the front.
- After a failed append, steps 5 and 6 append nothing more. Step 7 still sums, so the status row stays current. The next pass, 5 s later, retries the same record. A dead disk fills the queues in about seven minutes; then the producers drop and count.
- A pass drains queue A fully, then queue B. Lines stay in order within a thread. Across threads the reader orders by time.
- Step 6 reads the free space every 5 s. Under five minutes of frames it sets `freeSpaceUnderReserve`, and `recordFrame` refuses frames. Above it again, the flag clears.
- There is no line buffer. A span line is 110 bytes, an event line about 190. A 40-minute flight writes about 11 MB of text against 3.7 GB of PNGs, so nothing is compressed (item 4).

**The C form.** The writer formats each line inside one fixed buffer, 16 KiB, twice the record bound (`kWriterLineBytes`). The formatter stops at the buffer's end. A line that did not fit is written as far as it got, plus its newline. The reader skips it as unparsable, and `m_linesCut` counts it (item 4). A short append is truncated back to the line's start with `ftruncate`, so the file holds whole lines. The front and the pop are `SpscConsumerFront` and `SpscConsumerPop`.

**What went wrong, and what happens now.** The first form kept a retry queue of copied lines (W1). It wrote the retried lines out of order and had its own depth to tune. The owner's pseudocode replaced it. A later form restarted at step 2 when the flag was set during the pass. That skipped the clear and looped for ever; a blind check found it. Now the writer always returns to step 1. The pass once had nine steps. One wrote thread lines from a flag per thread. One checked the free space every 100 lines, with a line counter. The owner rejected both fields (RCD68). The thread line is now a queued record, and the free-space check sits in the 5 s step.

### 2.3 The wake flag: who sets it, what the writer does with it (drawing 3)
**The scheme, in the field's words.** A condition variable with a remembered notify is a flag under a mutex. A waiter sleeps until the flag is set or a timeout passes. A set when nobody waits is kept, so no wake is lost. The waiter clears the flag after it wakes. Python calls it `threading.Event`.

**Here.** Four sources set `recorder.consumer.wakeFlag`: a queue that crossed half full, a filled image buffer, Destroy and Die. The writer's step 1 is in `RecordWriter.run` above: wait 5 s at most, clear, pass.

**The Python form.**
```python
def wakeWriter():
    wakeFlag = recorder.consumer.wakeFlag
    if not wakeFlag.is_set():                                # 23 ns; a set costs 332 ns
        wakeFlag.set()


def wakeWriterIfHalfFull(before):                            # called by pushRecord
    if before < RECORD_QUEUE_WATERMARK <= before + 1:        # once per crossing
        wakeWriter()
```

**What the code does not show.**
- A set that lands during a pass stays in the flag. The next wait ends at once.
- A span alone never sets the flag. A wake is a futex call of 1.8 us, and a span costs 150 ns. The file is read after the run. A queue sets it once per crossing of half full (R4).
- A frame sets it every time. A pool has 8 buffers and an encode takes 40 ms, so 5 s would fill it.
- `is_set` before `set` saves 300 ns when the flag is already set (item 16).

**The C form.** The header names the primitive by its role, `OsEvent`, with set, clear, is-set and a timed wait. That is a placeholder in a contract header, not a portability layer we build. A condition variable with a remembered notify is made differently on Linux, Windows and macOS. The Python build uses `threading.Event`.

**What went wrong, and what happens now.** Telemetry's first writer polled every 10 ms (RCD6: "Why is the recorder polling?"). The flag replaced the poll. Drawing 2 once drew two return arrows, into step 2 on "set" and into step 1 on "not set". That form skipped the clear. Now the drawing has one return arrow into step 1 (RCD30, "P3 - Good").

### 2.4 A frame: the image buffer pool, from the shared frame buffer to a PNG (drawing 4)
**The scheme, in the field's words.** Two standard pieces make the pool. The first is an object pool. That is a fixed set of N equal buffers, allocated once, with a free list of the unused ones. The second is a producer-consumer work queue: the filled buffers, oldest first, waiting for the one consumer. A producer takes a buffer from the free list, fills it, and enqueues it. The consumer peeks the oldest, processes it, dequeues it, and returns it to the free list. Two buffers is double buffering, or ping-pong. V4L2 calls the same shape a buffer queue, with QBUF and DQBUF. A buffer in neither queue belongs to the one thread that holds it, so no per-buffer ownership state exists.

**Here.** The producers are the vision job threads, up to eight. The pixels come from the frame buffer, a separate component (module 04), one shared-memory block of slots. A job holds its latest slot. The SAM3 process reads the same slot and replies with masks. `recordFrame` copies the pixels from the held slot into an image buffer of the recorder's own pool. Then the job releases the shared slot (RVW3). The consumer is the writer, and the processing is the PNG encode. The frame pool holds 8 BGR24 images and the mask pool 24 GRAY8 images. That is 8 times the 3 masks of a pass.

**The Python form.**
```python
def recordFrame(folderName, fileName, frameCaptureTimestamp, frame):   # frame: a FrameView
    dropUnit = ONE_MASK_DROPPED if frame.format == PIXEL_GRAY8 else ONE_FRAME_DROPPED
    producer = producerOfThisThread()
    refusal = refusalIfNotRecording(producer, dropUnit)
    if refusal is not None:
        return refusal

    pool = poolForFormat(frame.format)
    if pool is None:
        return RecordResult.NO_FRAME_POOLS                   # the SAM3 process records no images
    if not frameArgumentsValid(frame, folderName, fileName):
        return countAndRefuse(producer, dropUnit, RecordResult.INVALID_ARG)
    if recorder.health.freeSpaceUnderReserve:
        return countAndRefuse(producer, dropUnit, RecordResult.DROPPED)

    index = pool.takeFree()
    if index is None:
        return countAndRefuse(producer, dropUnit, RecordResult.DROPPED)

    fillImage(pool.buffers[index], frame, folderName, fileName, frameCaptureTimestamp)
    pool.enqueueFilled(index)

    countQueuedImage(producer, pool)
    emitPendingDropLine(producer)                            # a success of any kind closes a hole
    wakeWriter()                                             # every image wakes the writer
    return RecordResult.OK


def poolForFormat(pixelFormat):                              # None: this process has no pools
    if pixelFormat == PIXEL_GRAY8:
        return recorder.maskPool
    return recorder.framePool


def fillImage(image, frame, folderName, fileName, frameCaptureTimestamp):
    numpy.copyto(image.pixels, frame.pixels)                 # releases the GIL
    image.frameCaptureTimestamp = frameCaptureTimestamp
    image.folderName = folderName
    image.fileName = fileName


def countQueuedImage(producer, pool):
    if pool is recorder.framePool:
        producer.statistics.framesQueued += 1
    else:
        producer.statistics.masksQueued += 1


class ImageBufferPool:
    def __init__(self, count, height, width, channels):      # at Create only
        self.pixelBlock = numpy.empty((count, height, width, channels), numpy.uint8)
        self.buffers = [ImageBuffer(self.pixelBlock[i]) for i in range(count)]
        self.freeList = IndexQueue(count, range(count))
        self.workQueue = IndexQueue(count, ())

    def takeFree(self):                                      # None: every buffer is in use
        return self.freeList.pop()

    def enqueueFilled(self, index):
        self.buffers[index].frameCopiedInTimestamp = monotonicNow()
        self.workQueue.push(index)

    def peekFilled(self):                                    # None: the work queue is empty
        return self.workQueue.front()

    def dequeueFilled(self):
        self.workQueue.pop()

    def oldestCopiedInTimestamp(self):                       # 0 when empty; a racy pair, fine for a status row
        index = self.workQueue.front()
        return 0 if index is None else self.buffers[index].frameCopiedInTimestamp

    def returnFree(self, index):
        self.buffers[index].status = PngOnDiskStatus.WRITE_PENDING
        self.freeList.push(index)


class RecordWriter:
    def drainPools(self):                                    # step 5 of the pass
        for pool in (recorder.framePool, recorder.maskPool):
            if pool is not None and not self.drainPool(pool):
                return False
        return True

    def drainPool(self, pool):
        index = pool.peekFilled()
        while index is not None:
            if not self.writeImage(pool.buffers[index]):
                return False                                  # the image stays at the front
            pool.dequeueFilled()
            pool.returnFree(index)
            index = pool.peekFilled()
        return True

    def writeImage(self, image):                             # the PNG once, then its frame line
        if image.status == PngOnDiskStatus.WRITE_PENDING:
            image.status = self.writePngToDisk(image)        # the status stays on the image
        ok = image.status == PngOnDiskStatus.WRITTEN
        return self.append(frameLine(image, ok))
```

**What the code does not show.**
- The pixel memory is one contiguous block per pool, allocated once. Each `ImageBuffer` views one slice of it; the pixels never move.
- `frameArgumentsValid` runs before the take, so the fill cannot fail. `folderName` is one or two names joined by one "/", at most 63 characters, without "..". `fileName` has no "/" and is at most 31 characters. The size, the format and the stride must match the pool.
- The copy exists so that no shared slot is held while the writer encodes for 40 ms. The job releases the slot right after `recordFrame` returns (RVW3).
- `writePngToDisk` makes the folder, opens the PNG with `O_EXCL`, and writes it at compression level 1 (TEL16). A name that exists already is `NAME_CLASH`, counted. A failed write is unlinked and counted in `pngFailures`.
- The status stays on the image. A failed append of the frame line leaves the image at the front. The next pass skips the encode and keeps the ok value.
- A full pool means a stuck writer. The writer is 27 % busy at 3 passes a second at 1080p.

**The C form.** The same types, in `index_queue.h` and `image_buffer_pool.h`. `IndexQueuePop` and `IndexQueueFront` return `INDEX_NONE` when empty; each takes the queue's lock inside. The pixel block is `uint8_t* m_pixelBlock`; each `ImageBuffer.m_pixels` points into it.

**What went wrong, and what happens now.** The first form had a per-buffer state with a compare-and-swap in C and a deque in Python. That was two mechanisms for one model. A lock-free queue measured 9,836 ns an operation in Python, against 255 ns locked. The owner ruled the lock (item 1, RCD50). The names "FramePool", "slot", "claim", "publish" and "release" said nothing of the scheme. They are gone; the types now say what they are (RCD54). A failed frame-line append once had nothing left at the front, since the buffer was dequeued before the line. Now the writer peeks, encodes once, appends, then dequeues. Two pool counters, takes and refusals, duplicated the producer's `framesRecorded` and `framesDropped`; they are gone (RCD68).

### 2.5 The statistics: who counts what, who sums it (drawing 6)
**The scheme, in the field's words.** Program statistics are named integer counters. Every actor keeps its own, and only that actor writes them. Where another thread must read them, the counters sit under a mutex held short, and the reader copies them whole. A copy taken under the mutex is never torn. The aggregate for a status row is the sum of the copies.

**Here.** Every producer counts what it queued and what was dropped, by kind: spans, events, frames, masks. The writer counts lines, bytes, failed writes, cut lines, PNGs, PNG failures, name clashes and flushes. The writer sums the producers' copies into the health at the end of each pass. The main thread reads the health once per frame.

**The Python form.**
```python
class RecordWriter:
    def endOfPass(self, copies, appendsOk):                  # step 7
        health = recorder.health
        before = health.copy()
        health.producersTotal = sum(copies, RecordingThreadStatistics())   # each store atomic; the set not
        health.consumer = self.statistics.copy()
        if not appendsOk:
            return
        for key, value in changedFaultFields(before, health):
            self.append(faultLine(monotonicNow(), key, value))       # T1
```

**What the code does not show.**
- A producer's eight counters have one writer, the thread, and no lock. In C the increments and the writer's copy are relaxed atomics. The writer never writes a producer's counters; what the deadline cuts off is its own count (2.7).
- The health is the aggregate: the sum over the producers and a copy of the writer's counters. The writer stores it field by field; the main thread reads it field by field. Each field is atomic, the set is not. A torn read shows a status row one pass stale, corrected at the next frame.
- The fault line fires only for a fault counter or a flag. Those are the dropped counts, `failedAppends`, `linesCut`, `pngFailures`, `pngNameClashes` and the two cut-off counts. The flags are `lastAppendFailed` and `freeSpaceUnderReserve`. Throughput counters never fire it (TEL2, T1).

**The C form.** Every statistics struct is a struct of `RecordCount`, in `recorder_statistics.h`. `StatisticsAdd`, `StatisticsSubtract` and `StatisticsAny` in `00-util/statistics.h` walk a struct as an array of counters. Every shared counter is accessed with relaxed atomic builtins; no lock. `OsLock` in the headers is a placeholder for a mutex, named by its role; the Python build uses `threading.Lock`.

**What went wrong, and what happens now.** The first form packed the drop gap into atomics with a sequence check. The owner: "Use a lock for crying out loud. Keep the lock being held short" (item 12). The queue once carried a drop count of its own, a second home. It is gone. A dropped-records type then stood apart, under four names in four places. The holes in the trace were merged per pass. The owner: "THIS IS PART OF STATISTICS! GENERAL PROGRAM STATISTICS!" (RCD66). Now every actor keeps one statistics object, and every hole reaches the file as a drop line.

### 2.6 The stop request: who changes the recorder's state, and how
**The scheme, in the field's words.** Terminate-and-join is the standard way to stop a worker thread. The owner sets a stop request, wakes the worker, waits for its "stopped" signal, and joins it. The state is a small machine under one lock: NOT_CREATED, RUNNING, STOPPING, STOPPED. The data a stop needs is stored before the state, so a worker that sees the state sees complete data. In C that is a release store seen by an acquire load: publish the data, then raise the flag.

**Here.** Two functions of the recorder itself change the state to STOPPING. `destroy` is called by the app in its close order. `flushInDie` is called by Die as its flush step. Both go through one internal function under `recorder.stateLock`, in both builds (item 10). The writer reads the state at the top of each pass and stops itself with its last pass (2.7).

**The Python form.**
```python
def requestStop(dieReason, drainDeadline):                   # the one internal function; both callers
    with recorder.stateLock:
        if recorder.state != RecorderState.RUNNING:
            return recorder.state                            # STOPPING: the caller waits; else: it returns

        recorder.consumer.dieReason = dieReason              # the writer reads both after it sees STOPPING
        recorder.consumer.drainDeadline = drainDeadline
        recorder.state = RecorderState.STOPPING

    wakeWriter()
    return RecorderState.STOPPING


def destroy(timeoutS):                                       # the app, in its close order
    drainDeadline = monotonicNow() + secondsToNs(timeoutS)
    state = requestStop("", drainDeadline)
    if state == RecorderState.NOT_CREATED:
        return False

    consumer = recorder.consumer
    stoppedInTime = consumer.stoppedFlag.wait(timeoutS)
    if not stoppedInTime:
        return False                                         # nothing stored; the state stays STOPPING

    consumer.thread.join()
    freeImagePools()                                         # the recorder's two pools; nothing touches them now
    recorder.outputFile.close()
    return True


def freeImagePools():
    recorder.framePool = None
    recorder.maskPool = None


def flushInDie(unusedCtx, reason, deadline):                 # Die step 3; a DieActionFn
    consumer = recorder.consumer
    if threading.current_thread() is consumer.thread:
        return                                               # one thread never waits for itself

    state = requestStop(reason, deadline)
    if state in (RecorderState.NOT_CREATED, RecorderState.STOPPED):
        return

    consumer.stoppedFlag.wait(nsToSeconds(deadline - monotonicNow()))
```

**What the code does not show.**
- Destroy's drain deadline is now plus its timeout. Die's is Die's flush cap, 5 s.
- A Die that finds STOPPING, during a Destroy, waits until its own deadline. The file gets no die line; the hand-over log has the reason.
- A Destroy past its timeout frees nothing: the writer may still touch the pools. The process exit reclaims them.

**The C form.** The state is `_Atomic RecorderState`, stored with release order under `m_stateLock`, the one lock of the recorder's lifetime. The writer loads it with acquire order. The reason is `DieReasonText`, 256 bytes; the deadline is `_Atomic MonotonicNs`. Destroy joins the thread, then `ImageBufferPoolDestroy` on both pools.

**What went wrong, and what happens now.** Destroy once moved the state by a compare-and-swap before the deadline was stored. A writer woken by its timer could see STOPPING with no deadline. Die once stored STOPPING over STOPPED and waited 5 s for a writer that was gone. The lock closes both (RCD59, item 9).

### 2.7 The last pass: what the writer does after a stop request (drawing 5)
**The scheme, in the field's words.** A bounded drain on shutdown means the worker empties every queue it owns, or stops at a deadline. Then it writes its final summary and signals "stopped". OpenTelemetry's ForceFlush and Shutdown follow the same rule.

**Here.** `RecordWriter.run` calls `lastPass` when it reads STOPPING. The records queued before the stop request explain a Die, so they must reach the file (item 5).

**The Python form.**
```python
class RecordWriter:
    def lastPass(self):
        self.drainUntilEmptyOrDeadline(self.drainDeadline)   # read once; complete (2.6)
        copies = self.countWhatRemains()
        self.writeClosingLines(copies)

        recorder.state = RecorderState.STOPPED
        self.stoppedFlag.set()

    def drainUntilEmptyOrDeadline(self, deadline):
        while not self.everythingEmpty() and monotonicNow() < deadline:
            appendsOk = self.drainEverything()               # steps 2 to 5, once
            if not appendsOk:
                time.sleep(1.0)                              # the disk may come back

    def countWhatRemains(self):                              # the writer's own count of the cut-off
        producers = recorder.producers
        for producer in producers:
            self.statistics.recordsCutOffAtDeadline += len(producer.recordsToWriter)
            producer.recordsToWriter.clear()

        for pool in (recorder.framePool, recorder.maskPool):
            if pool is not None:
                self.statistics.imagesCutOffAtDeadline += pool.discardFilled()

        for producer in producers:                           # a hole still open becomes its line
            line = takePendingDropLine(producer)
            if line is not None:
                self.append(formatRecord(producer.threadIndex, line))

        return [producer.statistics.copy() for producer in producers]

    def writeClosingLines(self, copies):
        if self.dieReason:
            self.append(dieLine(monotonicNow(), self.dieReason))
        self.endOfPass(copies, True)                         # step 7: the sums, the fault lines
        self.append(timeReferenceLine())                     # step 6, unconditionally
        self.append(healthLine(recorder.health))
        recorder.outputFile.flushToDisk()
```

**What the code does not show.**
- `drainEverything` is steps 2 to 5 of `onePass`. A failed append ends that iteration; the loop sleeps 1 s and repeats until the deadline. `discardFilled` dequeues and returns every filled image of a pool and returns their count.
- A record call after the stop request is dropped and counted by its own thread (RCD34 B2). What the deadline cut off is counted by the writer, in its own two counters. So the queues and the pools are empty at STOPPED.
- One hole remains, for Die only. A job thread loads RUNNING and is preempted before its append. The writer drains everything, finds every queue empty, and stores STOPPED. The thread resumes and appends. That record is never written and never counted. It needs a push inside the microseconds between the last empty check and the STOPPED store. At 40 records a second that is about one Die in 25,000, and one record. Destroy has no such hole: the app closes its modules first, so no thread records then.
- The final time reference and health line are written even after a failed drain. So a reader has the totals.

**The C form.** The same sequence inside `RecordWriterRun`. The deadline is `m_drainDeadline`; the signal is `m_stoppedFlag`, an `OsEvent`.

**What went wrong, and what happens now.** Before item 5 the last pass drained each queue once. A record pushed after the writer passed its queue was counted as dropped and never written. The owner: "Wait for all pending operations to be done, then Actually die()". Now the drain runs to empty or to the deadline.

### 2.8 The health: who reads it, and the stall question (drawing 6)
**The scheme, in the field's words.** A status aggregate has one writer and one reader on another thread. The writer stores it under a lock held short; the reader copies it whole under the same lock. A flag that depends on the clock is computed at read time, not stored.

**Here.** `RecorderHealth` (section 2.0) is the status row's data, the aggregate of section 2.5. The writer alone stores it. The main thread reads it once per frame. `stalled` is computed at read.

**The Python form.**
```python
def readHealth():                                            # the main thread, once per frame
    health = recorder.health.copy()                          # field by field; each read atomic
    health.writerStalled = writerStalled(monotonicNow())
    return health


def writerStalled(now):                                      # the writer took no filled image for 5 s
    for pool in (recorder.framePool, recorder.maskPool):
        if pool is None:
            return False
        copiedInAt = pool.oldestCopiedInTimestamp()          # section 2.4
        if copiedInAt != 0 and now - copiedInAt > WRITER_STALL_NS:
            return True
    return False
```

**What the code does not show.**
- `writerStalled` answers one question for the status row: has the writer stopped taking filled images? Five seconds on the work queue means a stuck writer. The cause is an encode that does not return, a hung disk write, or a dead thread. A live writer empties a pool in 320 ms.
- The pool's front index and that image's copy time are two reads, not one unit. A dequeue between them pairs an old index with a fresh time, and the stall shows one frame later. For a status row that is fine; no lock.
- The threshold equals the wake period on purpose. A filled image sets the wake flag, so a live writer wakes within microseconds.

**The C form.** `RecorderHealth` in `recorder.h` is the value; the instance holds it. Every field is stored and loaded with relaxed atomic builtins; no lock. `RecordWriterIsStalled` takes the pool's answer and the clock.

**What went wrong, and what happens now.** The writer once stored the oldest buffer's copy time at the end of each pass. A writer stuck inside a pass never reaches the end. So the stored time went stale, and the stall was never reported. Then a "last progress" stamp of the writer entered the rule, for a writer that is slow but alive. Eight buffers cannot produce that case, so the stamp is gone (RCD68). A health lock and a queue lock for the read came and went the same day (RCD74). A status row may be one frame stale. Now the pool answers from its own work queue, and the rule is one comparison. "Degraded" of telemetry became two flags with their own recovery: last write failed, and free space under reserve (D13).

### 2.9 The lifetime: Create, one per process, and Destroy (drawing 5)
**The scheme, in the field's words.** A service with one instance per process is created once at start. It is destroyed once at close. Everything it needs is allocated at Create, so no path after start allocates or fails for memory. Every bound is checked where the value enters, in every build. Every thread that uses the service registers at its start and unregisters at its end.

**Here.** `create` runs once per process, at the app's start, as the first service. `destroy` is in section 2.6. Registration is in section 2.1. The SAM3 server passes no frames and gets no pools.

**The Python form.**
```python
def create(sessionDir, processName, infoJson, frames):       # frames: a RecorderFrameConfig or None
    if recorder.state != RecorderState.NOT_CREATED:
        return False                                         # one Create per process
    if not argumentsWithinBounds(sessionDir, processName, infoJson):
        return False

    if not openSessionFiles(sessionDir, processName):
        return False                                         # unwritable, or the file exists
    makeProducers()
    if frames is not None and not makeImagePools(sessionDir, frames):
        return False                                         # under the reserve

    recorder.outputFile.writeHeader(infoJson, frames)        # the time reference, the info line
    startWriter()
    return True


def argumentsWithinBounds(sessionDir, processName, infoJson):   # the same bounds in both builds
    if len(sessionDir) > SESSION_DIR_MAX:
        return False
    if len(processName) > PROCESS_NAME_MAX:
        return False
    return len(infoJson.encode()) <= INFO_JSON_MAX


def openSessionFiles(sessionDir, processName):
    os.makedirs(os.path.join(sessionDir, "asr_clips"), exist_ok=True)
    recorder.sessionDir = sessionDir
    recorder.processName = processName
    return recorder.outputFile.create(sessionDir, processName, os.getpid())


def makeProducers():                                         # everything a producer needs, now
    recorder.producers = [RecordingThread(i) for i in range(RECORDING_THREADS_MAX)]
    recorder.nextProducerIndex = itertools.count()
    recorder.threadLocal = ProducerSlot()


def makeImagePools(sessionDir, frames):
    if freeBytes(sessionDir) < reserveBytes(frames.size, WRITER_FLIGHT_MINUTES):
        return False
    recorder.expectedFrameSize = frames.size
    recorder.framePool = ImageBufferPool(FRAME_POOL_BUFFERS, frames.size.height, frames.size.width, 3)
    recorder.maskPool = ImageBufferPool(MASK_POOL_BUFFERS, frames.size.height, frames.size.width, 1)
    return True


def startWriter():
    recorder.consumer = RecordWriter()
    recorder.consumer.thread = threading.Thread(target=recorder.consumer.run, daemon=True)
    recorder.state = RecorderState.RUNNING
    recorder.consumer.thread.start()
```

**What the code does not show.**
- The three bounds are maximum lengths, the same in both builds (item 14). The two frame bounds of `recordFrame` are buffer sizes: 64 and 32 bytes, texts of at most 63 and 31.
- Nothing is allocated after Create. In C that is 16 queues of about 1 MiB, static. In Python a deque grows by one tuple per record and shrinks when the writer pops: bounded, not static. The normal fill is about 200 records between two passes.
- The reserve is W x H x 3 x 0.45 x 30 passes a minute x the minutes. Create refuses the start under 40 minutes of frames (TEL17); the writer refuses frames under 5 minutes.
- The session folder is the app's, made before any child launches. `asr_clips/` is the recorder's (RCD34 A1).
- The app closes its modules first, so every recording thread has unregistered before `destroy`. The writer is a daemon thread, so a `destroy` past its timeout still lets the process exit (item 15).

**The C form.** The bounds are `kRecorderSessionDirMax`, `kRecorderProcessNameMax` and `kRecorderInfoJsonMax` in `recorder.h`. The instance is `struct Recorder` in `recorder_internal.h`, file-static. `RecorderRegisterThread` and `RecorderUnregisterThread` fill and clear `tls_producerOfThisThread`; the registration is one `atomic_fetch_add` on `m_nextProducerIndex`.

**What went wrong, and what happens now.** The first form made a thread's queue at its first record. The owner: "Why do you lazy init? We said to preallocate" (item 8). A reset list for a second Create existed; it is gone, since nothing is created twice. The bounds were checked in C only. The owner: a missing length check is a failure in Python too (item 14). A thread's entry was assigned by its first record, through a thread-local object that nobody initialized. The owner: "someone must come and initialize it" (RCD67). Now a thread registers and unregisters, like everything else with a lifetime.

### 2.10 The drawings, and the files of a process
The drawings are in `recorder.html`: six, one per path. Each shows a box per thread inside the process box. The structures and operations are generic, with the code name after a tilde (RCD25, RCD28, RCD29, RCD30). Each measures zero faults in the diagram tools. The sources are the session scratchpad `rec6/*.dot`.

| drawing | the mechanism | code names |
|---|---|---|
| 1 the push | section 2.1 | RecorderRegisterThread, RecordSpan, RecordEvent, RecordingThreadPushSpan, RecordingThreadWakeWriterIfHalfFull |
| 2 the pass | section 2.2 | RecordWriterRun, RecordWriterFormatRecord, RecordFileAppendLine, RecordFileFlushToDisk |
| 3 the wake | section 2.3 | RecordWriter.m_wakeFlag, OsEventSet, OsEventIsSet, OsEventWait, OsEventClear |
| 4 a frame | section 2.4 | RecordFrame, FrameView, BufferPoolTakeFree, BufferPoolEnqueueFilled, BufferPoolPeekFilled, BufferPoolDequeueFilled, BufferPoolReturnFree |
| 5 the lifetime | sections 2.6, 2.7, 2.9 | RecorderCreate, RecorderDestroy, RecorderFlushInDie, RecordWriter.m_stoppedFlag |
| 6 the health | sections 2.5, 2.8 | RecordingThreadStatistics, RecordWriterStatistics, RecorderHealth, RecorderReadHealth, ImageBufferPoolOldestCopiedInTimestamp, RecordWriterIsStalled |

The files of a process: `record-<process>-<pid>.jsonl`, one JSON line per record; the frames under `<folder>/<name>.png`, the masks beside them. The actors by prefix: RecordingThread, ImageBufferPool, RecordWriter, RecordFile; every actor has its Statistics.

**Several processes, one session folder.** The app creates the session folder before any child launches. Its mkdir fails if the folder exists. It passes the path in the child's argv. Each process creates its own instance and opens its own file exclusively. The file name carries the process name and the pid. Only the app has pools, so every record file has one writer. A file is append-only. Create writes its two header lines; then the writer thread alone appends, with a flush every 5 s. The reader merges every `record-*.jsonl` of the folder by each file's time reference lines.

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start, the screen's frame span, a turn's event.** The field names are
string literals; the hot path passes numbers and names, and builds no JSON of the recorder's; a caller's text field (the boxes list) is the caller's.
```python
# app/main.py, the first service; the size probe ran before this
size = frame_source_size(config)
if not recorder_create(session.dir, "app", info_json, RecorderFrameConfig(FrameSize(size.w, size.h))):   # false: see below
    die("the session folder is unwritable or under the free-space reserve")
die_add_flush(recorder_flush_in_die, None)             # Die step 3, under the 5 s cap

# app/record_screen.py, the screen's helper: its field names are plain strings

FRAME_SPAN_NAMES = ("read", "draw", "show")               # the names, once, per helper

def record_frame_span(t0, t_read, t_draw, t_end):       # the helper: numbers in, no text
    record_span(SPAN_FRAME, t0, t_end, FRAME_SPAN_NAMES,  # one tuple into the deque (PY3)
                (ms(t_read - t0), ms(t_draw - t_read), ms(t_end - t_draw)))


# app/screen.py, the main thread, every frame
t0 = monotonic_now()
frame = frames.acquire_latest(); t_read = monotonic_now()
draw(frame, views, panes); t_draw = monotonic_now()
cv2.waitKey(1); t_end = monotonic_now()
frames.release(frame)
record_frame_span(t0, t_read, t_draw, t_end)
health = recorder_read_health()                          # ten values, like a status row
```
**Instance 2: one SAM3 request, in the app and in the server, joined by `req`.**
```python
# perception/jobs.py, a job on a pool thread (the app process)
slot = frames.acquire_latest()                           # held across the request (RVW3)
t0 = monotonic_now()
reply = sam3.detect(req, slot.seq, concepts, priority)
t1 = monotonic_now()
record_span(SPAN_SAM3_REQUEST, t0, t1, SAM3_REQUEST_NAMES, (req, priority, reply.ok))
record_vision_pass(VisionPass(job, req, t0, t1, slot, concepts, reply))   # frames, masks, one event
frames.release(slot)                                     # the pools copied, or dropped and counted

# inside the helper: one struct per frame or mask; the pixels stay the caller's during the call
record_frame(folder, name, slot.captured_at, FrameView(PIXEL_BGR24, slot.size, slot.stride, slot.pixels))
for k, mask in enumerate(reply.masks):
    record_frame(folder, f"{name}_mask_{k}", slot.captured_at, FrameView(PIXEL_GRAY8, slot.size, slot.size.width, mask))
record_event("pass", t0, PASS_NAMES,                   # job, req, phrase, boxes, png
             (job.id, req, concepts, boxes_json(reply), name))

# sam3/server.py, its own process: spans only, no frame pools
if not recorder_create(session_dir, "sam3", "{}", None):
    die("the session folder is unwritable")
t_start = monotonic_now()
boxes = model.detect(block.pixels(request.seq), request.concepts)
t_end = monotonic_now()
record_span(SPAN_SAM3_PASS, t_start, t_end, SAM3_PASS_NAMES, (request.req, wait_ms, len(boxes)))
```
A helper lives in the module that owns the record, in that module's own header (RecordLlamaRequest in llama_server.h, RecordVideoRow in frame_source_internal.h): one
function per span or event that reads as a sentence; the field names are string literals. The helper
takes no recorder argument and builds no JSON of the recorder's.

## 4. The rulings that bind it, and the forces
| ruling | the owner's words | here |
|---|---|---|
| the merge (2026-10-18) | "Both telemetry and perf need to write to some file ... Albeit with different requirements" | one service, three contracts; one queue per thread and two buffer pools (RCD11, PY3) |
| the names (2026-10-18) | "Call it RecorderCreate() and destroy(), recordSpan(), recordEvent(), recordFrame(), and so on" | RecorderCreate, RecorderDestroy, RecordSpan, RecordEvent, RecordFrame |
| no handle (PRF7, 2026-10-18) | "Why do you hold a handle to m_perf?" | ambient: no handle returned, none passed |
| RVW4 | one process-wide tracer with a ring per thread | one instance per process; one queue per thread |
| PRF2 to PRF6 | the span ring, the 128-byte record, the time reference line, the drain, the thread cap | the cap unchanged; the time reference line re-emitted every 5 s (R4); the ring, the 128-byte record and the drain replaced by RCD11, PY3 and the writer's pass (the dated record) |
| TEL1 to TEL3 | a generic sink, no domain type, no app state, no die() | the sink rule unchanged; TEL1's opaque logger became the ambient instance (RCD1); TEL3's JSON string became typed fields (R4, RCD11) named by literals (K1) |
| TEL5, TEL13, TEL16 | lossless PNG level 1 at the source's resolution | unchanged |
| TEL17 | the free-space rule and the reserve | unchanged: Create refuses the start under 40 minutes of frames (TEL13); the writer stops frames under 5 minutes; spans and events never stop |
| TEL2 | the sink never kills the app | unchanged; the one die is the 17th thread (RVW4). TEL2's "one event" per fault is the fault line the writer writes itself (T1, 2026-10-22) |
| REV8, gate item 12 | a cause before any mechanism | every row of the failure matrix below names its cause |
The forces are the measured ones: a Python span costs 150 ns (PY3); a PNG of
a 720p frame costs 37 to 41 ms in the writer; the 330 us main-thread budget per frame; the
sessions ran 4 to 32 passes a minute.

## 5. The design gate, the deltas against the two approved gates
Each row names the mechanism of section 2 that meets the item. The tables under it hold the contract, the races and the failures. They name a mechanism; they do not restate it.

| # | gate item | how the recorder meets it |
|---|---|---|
| 1 | the real-time path | a record call checks its field count, cuts a text past the bound, pushes one tuple, returns (section 2.1). No lock while the queue has room. A drop takes the producer's statistics lock (2.5). A half-full crossing takes the flag's lock inside the set (2.3). A frame takes the pool's two queue locks, one operation each (2.4). No text of the recorder's; no allocation in C. The frame copy is on the job thread |
| 2 | a sink | no domain type, no app state, no die() after start. The one ruled exception is the 17th recording thread, a bug of ours (RVW4, RCD19 item 2). The writer never records |
| 3 | fault containment | a failed append ends the pass; the record stays at the front; the next pass retries it (2.2). A short write is truncated to the line's start. A half PNG is unlinked. A full queue or pool drops and counts (2.1, 2.4). A text past 8 KiB is cut and marked, never refused (2.1). A maker's bad value stops the helper before any record call. Nothing touches the aircraft |
| 4 | buffer lifetimes | a shared frame slot is never held for the recorder. The pool copy happens while the job holds it (2.4, RVW3). A record is the producer's until its push and the writer's between front and pop. A text field's bytes are the caller's during the call only |
| 5 | types and units | every constant named with its unit; 64-bit values as macros; DurationNs, MonotonicNs; unsigned time compares. The C layout is the embedded form; Python stores a tuple (PY3). Test 1 formats both into the same line |
| 6 | one home | one instance per process (2.9). One writer thread per file; only it appends after Create's two header lines. The flags: O_CREAT, O_EXCL, O_APPEND, O_CLOEXEC. Create checks its bounds in both builds (2.9). RecordFrame checks a folder of at most 63 characters and a name of at most 31 (2.4). The pools are the app's only. A helper lives in its owner |
| 7 | the contract | the file, line by line, below. Every time is in monotonic nanoseconds unless the key says otherwise. Names, never ids. Every key is in record_file.h |
| 8 | the Python mapping | the Python form of every mechanism is in section 2, with its measured number in section 2.0; camelCase members and functions (the owner, 2026-10-24) |
| 9 | the cost budget | 40 spans a second on the main thread at 150 ns is 6 us a second. That is inside 1 % of the 33 ms frame. The writer formats a line in 2.9 us and writes it in 1.4 us, off the main thread |
| 10 | deterministic checks | the health counters unpadded on purpose (RCD31). gcc -Wall -Wextra -pedantic -std=c11 passes on all sixteen headers. Static asserts pin the field count to a byte and the record bound to 16 bits. One pins the C line buffer to twice the bound. The C queue's head and tail sit on their own cache lines. The six drawings measure zero faults |
| 11 | TOCTOU | the table under the contract |
| 12 | Need | every row of the failure matrix names its cause, or the ruling it stands on |

The lines of the contract (item 7):
```
{"k":"time","process":"app","pid":1001,"monotonic_ns":104523912,"wall_us":1729278000123456,"boot_ns":104523912}
{"k":"info","frame":{"w":1280,"h":720},"info":{"models":{...},"session":"...","host":"..."}}
{"k":"thread","t":0,"name":"main"}
{"k":"span","t":0,"s":"frame","a":104530001,"b":104540002,"p":{"read":1.2,"draw":8.4,"show":0.9}}
{"k":"event","t":0,"topic":"turn","at":104530001,"p":{"seq":12,"phase":"decided","kind":"highlight"}}
{"k":"frame","folder":"perception/0001-highlight","name":"000012","at":104530001,"ok":true}
{"k":"drop","t":3,"spans":0,"events":2,"frames":0,"masks":0,"from":104600000,"to":104650000}
{"k":"fault","at":104700000,"what":"failed_appends","count":1}
{"k":"health","producers_total":{"spans_queued":9120,"events_queued":31,"frames_queued":12,"masks_queued":36,"spans_dropped":0,"events_dropped":2,"frames_dropped":1,"masks_dropped":0},"consumer":{"lines_written":9163,"bytes_written":1104211,"failed_appends":1,"lines_cut":0,"pngs_written":11,"png_failures":1,"png_name_clashes":0,"flushes":3,"records_cut_off_at_deadline":0,"images_cut_off_at_deadline":0},"last_append_failed":false,"free_space_under_reserve":false,"free_space_gib":41.2,"writer_stalled":false}
{"k":"die","at":104990000,"reason":"..."}
```
The time reference line comes again before every health line. The event's "png" key is the request; the frame line is the proof. A reader skips and counts a line it cannot parse. The drop line is placed by its "from"; its count is since the last drop line. The order in a file is the writer's pass order (section 2.2). At the end it is the last pass order (section 2.7).

TOCTOU (item 11), each race and its answer:
| race | answer |
|---|---|
| a record call after Destroy began | the state is loaded once per call. RUNNING records. STOPPING and STOPPED drop and count (RCD34 B2). NOT_CREATED returns NOT_CREATED and counts nowhere. What the deadline cut off is counted by the writer before the final health line (2.7). A push by a producer that loaded RUNNING just before the final empty check stays in its queue. The window is microseconds |
| a push against the consumer | in C the producer loads the consumer's index with acquire every push. In Python the deque's append and popleft are one bytecode each (2.1) |
| the writer against a record under construction | in C the producer's index moves only after the record is stored, with release. In Python the tuple is whole before the append (2.1) |
| a pool buffer taken by two job threads | the index is popped from the free list under its lock (2.4) |
| the writer against a half-copied buffer | an index reaches the work queue only after the copy (2.4) |
| a new thread's queue seen before it exists | every entry exists from Create (2.9), and the writer walks all 16. Registration is one fetch-and-add; the name travels as the first queued record |
| the 17th thread's count | the writer walks at most the table's size (2.2 step 2) |
| a wake between the writer's state check and its wait | the set is remembered; the order is wait, clear, read (2.3) |
| a half-full wake lost while the writer runs | the remembered set survives; the next pass drains anyway (2.3) |
| the producers table read twice in one pass | the table is fixed; all 16 entries are walked each pass (2.2 step 2) |
| a producer's statistics read torn | the eight counters have one writer, the thread; in C relaxed atomics (2.5); a hole becomes a drop line in the queue, under its own lock (2.1) |
| a stop stored while the writer resumes | the stop request stores the reason, the deadline, then STOPPING under the state lock (2.6). The writer alone stores STOPPED. A Destroy past its timeout stores nothing |
| the free-space check against a write between the check and the PNG | the 5-minute reserve covers it (2.2 step 6) |

The failure matrix (item 12):
| failure | cause | the recorder's state | what it leaves | the aircraft |
|---|---|---|---|---|
| a disk write fails or is short | SEEN (a full disk in a session) | a short write is truncated to the line's start. The record stays at the front and the pass ends. The next pass retries it (2.2). A dead disk fills the queues in about seven minutes; then drop-new, counted | failed_appends, last_append_failed | never touched |
| a 5 s stall of the writer | DESIGNED, by ruling TEL10 (the owner's stall rule); frames only | writerStalled, computed at read from the pool's oldest copy time (2.8) | the health line | never |
| SIGKILL | FORCED | at most 5 s of records lost. The pools are lost: up to 8 frames and 24 masks whose events may name them. The PNGs on disk stay | a torn last line, skipped | never |
| a power cut | FORCED | the same, plus up to 35 s of PNGs never fsynced, and a new file's directory entry | the reader counts the missing frames | never |
| fsync succeeds after a writeback error | FORCED (a failing disk) | the data is lost; the kernel reports the error once | failed_appends, last_append_failed | never |
| a full queue | drop-new, by ruling (TEL7); 16,384 entries hold over six minutes at the measured 40 spans a second (RCD35) | counted, the gap stamped (2.5) | a drop line with the gap | never |
| a text past the record bound (8 KiB, RCD36) | SEEN at the old 4 KiB bound. 12 of 845 recorded passes were over 2047 bytes. The largest was 5849, which now fits | the text cut at a character, the record gains "cut" (2.1) | the line, complete but for the text | never |
| a full pool | drop, by ruling (TEL7); the writer is 27 % busy at 3 passes a second at 1080p | the frame dropped, counted in the job thread's statistics (2.4) | no frame line | never |
| a wrong frame size | DESIGNED (the probe against the source) | INVALID_ARG (2.4) | nothing | never |
| the session folder exists already | FORCED (a second app in the same second) | the app's mkdir fails before any Create; O_EXCL is the second guard | nothing | never airborne |
| a PNG name that exists already | DESIGNED (D10: a caller gives the same folder and name twice, a bug of ours) | the PNG is not written; counted in png_name_clashes; the frame line carries ok false (2.4) | the frame line | never |
| a 17th recording thread, a bug of ours | DESIGNED, by ruling (RVW4, RCD19 item 2; the dated record) | Die | the hand-over | the hand-over |
| under the reserve at start | SEEN (sessions on a full disk) | Create returns false; the app dies at start (2.9) | nothing | never airborne |

## 6. The notes that did not make the header
- **The Python form of the queue, measured (2026-10-19 and 20, PY3, RCD18).** Per push with two
  clock reads of about 100 ns: a tuple appended to a bounded deque 150 ns; a SimpleQueue 226;
  a packed bytes object in a deque 212 to 241; a literal byte ring with its rounding and padding
  runs 646; a deque under a shared mutex 264 to 429; a mutex and a condition-variable notify 593 to 758 (two runs, the later on a loaded machine). Four
  producers: their own deques 246 against one shared mutex deque 428. The owner ruled the
  fastest measured construct, whatever the C design wanted (PY3: "We will perform what is
  fastest"). The Python build uses the tuple deque; the C header keeps the ring of record
  slots with its byte area as the embedded form; both keep the contract: one producer, one
  consumer, bounded, drop-new.
- **Why not numpy for the per-thread queue (the owner asked, 2026-10-19).** Measured per push with two clock reads of 99 ns: a tuple in a deque 150 ns; struct.pack_into into a numpy byte ring 241; a numpy structured-array ring with a tuple assignment 384; six parallel typed-array assignments 451; a row assignment from a one-row array 787. Reading one record back: a deque tuple 34 ns, a structured record 309. Numpy is fast for one operation over many elements; one element at a time it boxes every scalar through Python. A scalar assignment holds the GIL like a deque append, so it buys no atomicity either. A fixed dtype also cannot hold a text field or a variable field count. Numpy stays where it wins: the frame pixel copy into a pool buffer, a large operation that releases the GIL.
- **Why typed fields and not a JSON string.** NanoLog logs in 7 ns because the hot path packs numbers and the formatting happens offline. Our measured pre-R4 Python span cost 723 to 804 ns, most of it the f-string. The field names travel with the record as string literals (K1: no registration table); the writer, which has time, makes the JSON the readers already expect. The file does not change.
- **Why a watermark wake.** A queue holds 16,384 records (a power of two, RCD35); the timer drains it every 5 s. A burst past half a queue wakes the writer early, as perf's wakeup watermark does and as OpenTelemetry exports early at a batch size (512 of 2048). The producer compares the count before and after its push and sets the remembered notify once per crossing. No measured rate reaches it (R3-4); it stands on the R4 ruling.
- **Why the time reference line again at every fsync.** Perfetto snapshots its clocks periodically during the run. A stepped wall clock (NTP, a resume) then shows in the file, and the reader aligns the three clocks per segment.
- **Why the drop line carries the gap.** ULog writes a dropout with its duration. A count says how many; the first and last time say when, which is what a reader needs to judge a trace.
- **Why one writer thread, not two.** A PNG encode of 40 ms delays only the next PNG. The span
  and event drain runs every 5 s and reads queues that hold minutes of records at the measured
  rates; a 40 ms delay is nothing to it. Two writers would add a second file handle and a
  second fsync for no measured gain.
- **Why the record queue and the index queue are util, not recorder.** The record queue knows nothing of spans; the queue knows nothing of PNGs. Each has its own invariants and functions, and other modules will want them. So each has one home in util, and the recorder only uses them.
- **Why the types carry the concurrency contract.** A plain queue pointer says nothing about who may push. So the queue hands out two endpoint types at Create, SpscProducer and SpscConsumer, and a thread that holds a producer cannot pop. The name says the model: SpscRecordQueue. The index queue says its model by its struct: a lock, so any threads. The owner, 2026-10-19: "Why is it not clear that the ring_buffer is SPSC?"
- **Why the head and the tail sit on separate cache lines.** Coherency moves 64-byte lines. With the two counters on one line, every push invalidates the consumer's line and every pop the producer's. At our rates that costs nothing measurable, but the layout would lie about the hardware. The read-only fields sit before both index lines, as rigtorp does. The read-only fields, then head and tail on their own lines: 192 bytes a queue, 3 KiB for 16. The Python deque has no such layout; the GIL serializes it.
- **Why a span does not wake the writer by itself.** A wake is a futex call, 1.8 us measured when the writer sleeps; a span costs 150 ns. The file is read after the run, so a span may wait 5 s. Only a queue that crosses half full wakes the writer, once per crossing. A frame wakes the writer every time, because a pool has 8 buffers and the encode takes 40 ms; waiting 5 s would fill it.
- **Why the instance reads.** Everything is allocated at Create (the owner, 2026-10-22: no lazy initialization): the table of 16 entries with their queues, the pools, the line buffer. A thread's first record claims the next entry, an index, not an allocation: under the state Lock in Python, by an atomic add in C. The writer's own state is the Writer member; the timer and the step counters are locals of the writer's one function.
- **Why the writer never records.** The writer writes the free space in its own health line; a record call from it would make it a recording thread under the cap.
- **Why the frame pools is optional at Create.** The SAM3 server records spans only. Its
  pools would be 44 MB of nothing.
- **What the field does.** OpenTelemetry: one SDK, three signals with their own APIs. Perfetto
  and Unreal Insights: one trace, many channels. Tracy: zones, messages and frame images in one
  stream, the images compressed off the hot path. PX4: one ulog with telemetry and perf counters.
- **The rejected alternatives** stay in perf.md and telemetry.md section 6.

## 7. The tests the module ships with (`test/test_recorder.py`)
One file, one test per row, grouped by actor. Each row names what it proves. From R4, Q1 and the three reviewer rounds; the two approved test lists of perf and telemetry are inside.

| # | actor | the test | proves |
|---|---|---|---|
| 1 | producer | the C record form and the Python tuple formatted into one line are equal | the two forms carry the same fields (item 5) |
| 2 | producer | 16,385 pushes into one queue: the last is dropped and counted; the writer reads 16,384 | drop-new at the bound (PRF4, RCD35) |
| 3 | producer | a 9000-byte boxes text gives one event line with "cut" = the bytes lost and valid UTF-8; a 5849-byte text is not cut | the cut rule at a character; the 8 KiB bound (RCD36) |
| 4 | producer | a record of 32 caller fields returns INVALID_ARG and is counted as dropped | the field cap of 31 |
| 5 | producer | a value of an unexpected type on the tuple path is written as its text; a maker given a bad value returns false (None in Python), the helper stops before any record call and returns the error to its caller; nothing is counted and nothing raises | no exception leaves the module |
| 6 | producer | a push that crosses half the queue sets the flag once; a second push past it does not; the count is true after a drain | one wake per crossing |
| 7 | producer | a 17th recording thread dies (RVW4); the writer's pass reads at most 16 entries | the thread cap |
| 8 | producer | a record before Create is a no-op | the state gate |
| 9 | writer | the writer's line of a span, an event, a frame, a drop equals the contract's line | item 7 |
| 10 | writer | a queue made, a drop, then FlushInDie with a reason: the thread line, the drop line, the die line, the fault line, the time reference line, the health line, in that order | the last pass |
| 11 | writer | a drop line carries the first and last dropped times | the gap |
| 12 | writer | the time reference line comes before every health line | item 7 |
| 13 | writer | a failed append, then 10 spans, then the disk recovers: the pass ended at the failure, the failed record stayed at the front, and the next pass writes it and the 10 spans in order | the retry without a retry queue (the owner, 2026-10-22) |
| 14 | writer | a short write once: the file holds only whole lines | ftruncate to the last whole line |
| 15 | writer | a span recorded while the writer encodes a PNG lands in the file within the next drain | one writer thread suffices |
| 16 | writer | a stop stored between the writer's state check and its wait ends the writer at once | the remembered set |
| 17 | pool | a bad stride returns INVALID_ARG and all 8 buffers stay on the free list | the checks before the take |
| 18 | pool | a writer stub that encodes during a slow copy never dequeues a buffer that is not yet on the work queue | enqueue after the copy |
| 19 | pool | the frame line follows the PNG | the proof after the fact |
| 20 | pool | Create with no frame config makes RecordFrame return NO_FRAME_POOLS | the SAM3 process has no pools |
| 21 | lifetime | a Create in a folder that already holds record-<process>-<pid>.jsonl returns false | O_EXCL |
| 22 | lifetime | a second Create in the same process returns false | one Create per process (the owner, 2026-10-22) |
| 23 | file | one file holds the time reference line, a span, an event and a drop line in time order | the merge rule |
| 24 | file | the reader of run.sh perf and the replayer read one sample session file | the readers still work |

## 8. Perf and telemetry, folded in (OPEN 4, done 2026-10-24, RCD77)
Perf (PRF3 to PRF5, 2026-10-12) and telemetry (TEL2 to TEL19, 2026-10-16) were two approved designs. They are one service now: this recorder. Their folders are gone. Their documents stay as frozen dated records in `../../test/perf-approved-2026-10-12.md` and `../../test/telemetry-approved-2026-10-16.md`. This section keeps what a builder or a reviewer still needs from them. That is the map of every contract and helper to its recorder form, the rulings, the measured forces, the rejected alternatives, and where their tests went.

### 8.1 The contracts and the helpers, mapped
The short labels used in this document: W1 was RCD25's retry queue, replaced on 2026-10-22 by the pass that ends at a failed append; K1 is RCD20's "no registration"; Q1 is PY3's tuple deque; U1 is RCD19's util headers (T1 is the fault line of the decision document); D1 to D14 are the blind reads' defects in docs/api-harden2/rev5/test/recorder-review.md; the ledger rows with the bare IDs W1, K1, Q1, T1, D1 to D14 belong to other work.
The owner asked for every function of the two approved designs that the recorder does not show, and whether it still matters. Three tables: the core contracts, the helpers, and the items with no recorder counterpart.

**The core contracts.** Every one has its recorder form.
| perf or telemetry | the recorder | ruling |
|---|---|---|
| PerfCreate(sessionDir, process) / TelemetryCreate(sessionDir, w, h, infoJson) | RecorderCreate(sessionDir, process, infoJson, frames or RECORDER_NO_FRAMES) | RCD1 |
| PerfDestroy / TelemetryDestroy(timeout) | RecorderDestroy(timeout) | RCD1 |
| PerfFlush / TelemetryFlushInDie(reason, timeout) | RecorderFlushInDie(unusedCtx, reason, deadline), a DieActionFn | RUN3 |
| TelemetryReadHealth | RecorderReadHealth; "degraded" became lastWriteFailed and underReserve (D13); pngNameClashes added (D10); droppedSpans added with the span contract (RCD1) | RCD1, D10, D13 |
| PERF_NONE, TELEMETRY_NONE, the pointer in every constructor | no handle: one ambient instance per process; a record before Create is a no-op (NOT_CREATED) | RCD1, PRF7 |
| PerfNow, PerfTimestamp | MonotonicNow, MonotonicNs in 00-util | OPEN 1 |
| PerfRecord(stage, start, end, payloadJson) | RecordSpan(stage, start, end, fields, count) | RCD1, R4 |
| TelemetryRecordEvent(topic, at, keysJson) | RecordEvent(topic, at, fields, count) | RCD1, R4 |
| TelemetryRecordFrame(channel, name, at, format, w, h, stride, pixels) | RecordFrame(folder, name, at, FrameView*) | RCD2 (FrameView), RCD22 (folder) |
| PerfStage (16 values incl. PERF_GPU) | SpanStage (15 values); PERF_GPU is DROPPED: no GPU record at all | RCD19, RCD34 (B1) |
| PerfStageKind SPAN or SAMPLE | gone: no sample contract | RCD4 |
| TelemetryResult OK, DROPPED, INVALID_ARG, DEGRADED | RecordResult OK, DROPPED, INVALID_ARG, NO_FRAME_POOLS, NOT_CREATED, returned by RecordSpan, RecordEvent and RecordFrame (RCD35, A2); DEGRADED gone: a failed append leaves the record at the front of its queue | RCD35, the owner 2026-10-22 |
| perf-<process>-<pid>.jsonl + trace.jsonl + meta.json | record-<process>-<pid>.jsonl, one file per process; meta.json's content is the time reference line and the info line | OPEN 2 |
| PerfClockLine monotonic, realtime, boottime | the time reference line: monotonic_ns, wall_us, boot_ns, again every 5 s | R4 |
| PerfThreadLine, PerfDropLine | the thread line; the drop line with the gap's first and last time | R4 |
| kPerfMaxThreads 32 | kRecordingThreadsMax 16 | PRF5 |
| kTelemetryWriterPollMs and the idle backoff | gone: the writer is event-driven | RCD6 |
| the free-space rule TEL17, the PNG ratio TEL16 | RecorderReserveBytes, the flight and reserve minutes, WRITER_PNG_BYTES_PER_RAW_BYTE | TEL16, TEL17 |

**The helpers.** TEL4 put them in headers of their own; the owner ruled each moves into its owner's header at that module's review ("Moves into the X module's header at its review"). The recorder keeps none (RCD21: one header per actor; section 3: "a helper lives in the module that owns the record"). Each helper's recorder form and its home:
| helper (perf, telemetry) | recorder form | home | state |
|---|---|---|---|
| PerfStartup(launched, up, row, restart) | RecordSpan(SPAN_STARTUP, ...) fields row, restart | runtime (03): the supervisor sees the launch and the first UP | not yet in runtime.h; at the fold |
| PerfMessage(enqueued, drained, kind, key) | RecordSpan(SPAN_QUEUE_MESSAGE, ...) fields kind, key | the dispatcher (11) | briefed; not started |
| PerfTurn(start, end, kind, turn) | RecordSpan(SPAN_TURN, ...) fields kind, turn | the dispatcher (11) | briefed; not started |
| PerfE2e(start, end, turn, from, to) | RecordSpan(SPAN_E2E, ...) fields turn, from, to | the dispatcher (11) | briefed; not started |
| PerfLlamaRequest + LlamaTimings | RecordLlamaRequest in llama_server.h | llama server (05) | DONE |
| PerfDjiRequest(path, status), PerfEmergency(turn, status) | RecordSpan(SPAN_DJI_REQUEST), RecordSpan(SPAN_EMERGENCY) | the phone client (07) | approved before the recorder; the UPDATE block of its brief names it; the helper lands at the fold |
| PerfSam3Pass(req, waitMs, boxes) | RecordSpan(SPAN_SAM3_PASS, ...) in the SAM3 process | the SAM3 server (06) | finished before the recorder; the UPDATE block names it; at the fold |
| PerfFrame(previousEnd, readStart, drawStart, showStart, end) | RecordSpan(SPAN_FRAME, ...) fields read, draw, show; the usage in section 3 | the screen, in the app (15) | not briefed |
| PerfGpu(at, memMiB, loadPct) | DROPPED (RCD19 item 7; RCD34 B1: "Not relevant") | none | closed |
| PerfSay(start, end, output) | RecordSpan(SPAN_SAY, ...) field output | speech out (09) | briefed |
| PerfSam3Request(req, prio, ok) | RecordSpan(SPAN_SAM3_REQUEST, ...) fields req, prio, ok; the usage in section 3 | the vision jobs (13) | not briefed |
| PerfJobStep(stage, job, result) | RecordSpan(SPAN_HIGHLIGHT_GATE or SPAN_OBJECT_COUNT or SPAN_DESCRIBE, ...) fields job, result | the vision jobs (13) | not briefed |
| TelemetryTurnDecided, TelemetryTurnEnded + TurnData | RecordEvent("turn", at, ...) twice, phase decided and ended, the same keys | the dispatcher (11) | briefed |
| TelemetryEvent + EventData | RecordEvent("event", at, fields kind, turn, job, detail) | the dispatcher (11) | briefed |
| TelemetryVisionPass + VisionPassData + TelemetryBox | RecordFrame for the frame and each mask, then RecordEvent("pass", ...) with the same keys; the usage in section 3 | the vision jobs (13) | not briefed |
| TelemetryJobStarted, TelemetryJobEnded + VisionJobData | RecordEvent("job", ...) twice, the same keys | the vision jobs (13) | not briefed |
| kTurnKinds, kEventKinds, kPassSteps, kJobKinds, kJobStates | the same tables, in the helper's header; a value is a field text (K1: no registration) | the dispatcher (11), the vision jobs (13) | with the helpers |
| RecordVideoRow in frame_source_internal.h | already on the recorder | the frame source (12) | DONE |

**No recorder counterpart.** Each with its verdict.
| item | where it was | verdict |
|---|---|---|
| <session>/asr_clips/ made at Create | TelemetryCreate | RecorderCreate makes <sessionDir>/asr_clips/ (RCD34 A1: the recorder records, so the folder is its); the session folder itself stays the app's, made before any child launches |
| session name and host in meta.json | TelemetryCreate | the info line carries what the creator passes; the app passes session and host in infoJson. No recorder change |
| the thread's native id in the thread line | PerfThreadLine | dropped: the file holds names; nothing read the native id. No change unless the owner wants it |
| a result returned by TelemetryRecordEvent | TelemetryResult | every record call returns a RecordResult (RCD35, A2); a drop is also counted in the health |
| the readers: run.sh perf's report (P25 to P99, C.1) and the replayer | perf.md, telemetry.md | they read record-*.jsonl at the implementation; test 24 pins it; no design change |
| the GPU reader (NVML; AMD on the desktop) | PerfGpu | DROPPED with the gpu event (RCD34 B1) |
| the writer's pause on a failed write and its resume | TelemetryHealth.m_degraded | replaced by the pass that ends at a failed append, the record left at the front, and the two flags; a fault line is written when a counter changes (TEL2) |

### 8.2 The rulings that came with them
Perf's rulings, each still in force through the recorder:

| ID | the owner's words | here |
|---|---|---|
| C.1 (2026-09-28) | "Record everything and calculate metrics later! Keep P25, P50, P75, P95, P99, min & max." | the recorder stores raw spans; the reader computes |
| R7 (2026-09-28) | "Make this configurable inside the config folder, default to 5s." | the flush period, `WRITER_FLUSH_TO_DISK_EVERY_NS` |
| V1 (2026-09-28) | "Option A" | the reader lists the 20 slowest frames |
| PRF1 (2026-10-02) | "PerfEvent@stage shouldnot be a string, unless you plan on chaining subEvents" | `SpanStage` is an enum |
| PRF2 (2026-10-04) | an opaque logger; "PerfTimestamp = raw ns"; "API does not track this. App does."; "Nobody actually writes a marker system like this." | no marks; the caller holds every start timestamp; `MonotonicNs` |
| RVW4 (2026-10-12) | one process-wide tracer with a ring per thread; "What about DLL/process Boundaries?" | one recorder per process; one queue per thread |
| RVW5 (2026-10-12) | "You can measure the C++ processes from our end ... as a single metric." | llama-server, the phone app and the keyboard hook are timed request to reply, in the app |
| RVW6, RVW7 (2026-10-12) | "Perfect." (a file per process, merged by the shared monotonic clock) | the SAM3 server writes its own file; the reader merges by the time reference lines |
| PRF5 (2026-10-12) | the thread cap is the design's count, not nproc | `RECORDING_THREADS_MAX` 16; the 17th registration dies |

Telemetry's rulings, each still in force or named where the recorder replaced it:

| ID | the ruling | here |
|---|---|---|
| TEL2 | never kill the app after start-up; drop, count, one event, a chat line | drop and count; the fault line (T1); the status row |
| TEL3, TEL4 | a generic sink; the records and the helpers live with their owners | one helper per span or event in the owning module's header |
| TEL5, TEL13, TEL16 | lossless PNG level 1, at the source's resolution | unchanged |
| TEL6 | the start-up check stays | Create returns false; the app dies at start |
| TEL7 | a full ring or pool: drop and count; a failed write: pause, count, resume; one trace file; the stop's reply as a message | drop and count; a failed append leaves the record at the front, retried each pass (RCD-era item 11 replaced the pause); one record file per process (OPEN 2) |
| TEL8 | the mic listener takes the newest clip name at the transcript | unchanged; `asr_clips/` is made by Create (RCD34 A1) |
| TEL9, TEL17 | the free-space rule from the frame size, the expected vision rate and the flight length | `RecorderReserveBytes`; 40 minutes at Create, 5 minutes for the writer |
| TEL10 | the trace fsynced every 5 s, the PNGs never; the stall rule | the flush step; `writerStalled` |
| TEL14 | no blob call; no N-th pass knob | unchanged |
| TEL11 | a thread past the cap is dropped and counted | REPLACED by RVW4: it dies (RCD19 item 2) |

### 8.3 The measured forces that came with them
Measured on this machine, in the telemetry rounds (2026-10-14 to 16) unless dated otherwise:
- A frame at 720p is 2.76 MB raw. A memcpy of it takes 0.05 to 0.18 ms. A PNG level 1 encode takes 37 to 41 ms. It gives 1.0 to 1.26 MB, 0.36 to 0.45 of raw. At 1080p: 6.2 MB raw, about 90 ms, 2.8 MB.
- A mask is one byte per pixel. Its PNG takes 3.5 to 4.3 ms and is 8 to 16 KB.
- JPEG q95 moved one SAM3 box in 16 and the scores by up to 0.086 over 40 images. So the images are lossless.
- The rates: a turn per 2 s. Vision runs at most 3 passes a second. The expected rate is 30 a minute; the recorded sessions ran 4 to 32, median 15.
- The writer's work at full load: 3 x 41 ms is 123 ms a second at 720p, 12 % busy. At 1080p it is 270 ms, 27 % busy. cv2 releases the GIL while it encodes.
- A write() returns in under 1 ms. An fsync of the record file costs 0.6 ms. This kernel's flusher runs every 5 s and writes back pages older than 30 s.
- The free-space rule at 1080p: 2.8 MB a pass. The start check is 3.4 GB, 40 minutes at the expected rate. The writer's reserve is 0.4 GB, 5 minutes. At 720p: 1.5 GB and 0.2 GB.
- The frame size is known before Create. The webcam is probed at start; the drone stream is 1920x1080; a video file is probed.
- Perf's own cost table of 2026-10-12 said 330 ns a packed record and 400 ns for an f-string payload. Section 2.0's table supersedes it: 150 ns a tuple push.
- Thread identifiers are recycled by Python and by Linux. So a thread finds its entry through its own thread-local pointer, never through an id lookup (section 2.1).

### 8.4 The alternatives they rejected, still rejected
- One shared array with an atomic fetch-add per record: a queue per thread needs no shared write (RVW4).
- Shared memory for the records across processes. A file per process and a merge by the clock give the same result (RVW6, RVW7).
- A binary record file: the reader and the tools read JSON lines; a binary file saves disk, not time.
- Blocking the recording thread on a full queue, or dropping the oldest. A timing tool never slows the step it times, and drop-new keeps the count (TEL7).
- A domain-typed sink: the sink stays the same when a schema changes; only a helper changes (TEL3).
- A failed write that dies: a logger has no authority over a vehicle (TEL2).
- Holding the shared frame slot until written, or waiting for a pool buffer. A stalled disk must not hold a slot (RVW3).
- A temp file and rename per PNG, a folder fsync, or an fsync pass over the PNGs. Each is a storm of up to 30 fsyncs a second for no measured gain.
- JPEG, raw, lossless WebP, packed bits for masks, hardware video encoders. The box moved, or the bytes doubled, or an image took 300 ms.
- A JSON per job and per pass. One stream of lines with a kind each is what MCAP and rosbag record.
- A reserve sized for full vision for an hour. It would refuse to start on a half-empty disk for nothing (2026-10-16).
- Polling the writer every 10 ms: the wake flag (RCD6).

### 8.5 Where their tests went
Perf listed 23 tests and telemetry 30. The recorder ships 24 (section 7); the rest moved or fell with their mechanism.

| group | from | where it is now |
|---|---|---|
| the push, the drop at the bound, the cut, the field cap, the thread cap | perf 1, 2, 7, 12, 16; telemetry 2, 3, 9 | recorder tests 1 to 7 |
| the writer: every record lands, the lines of the last pass, the drop line, the retry after a failed append, whole lines | perf 1, 3, 13, 14; telemetry 10, 11, 12 | recorder tests 9 to 16 |
| the pools: the separate mask pool, the copy before release, the frame line after the PNG, no pools in the SAM3 server | telemetry 4, 5, 6, 7, 8 | recorder tests 17 to 20 |
| the lifetime: O_EXCL, one Create per process, Destroy with a stuck writer, the die line | perf 4, 5, 6; telemetry 13, 14, 15 | recorder tests 10, 21, 22 |
| the file: the time reference first, the merge of two processes by the clock, a torn last line | perf 13, 18, 19; telemetry 25 | recorder tests 12, 23, 24 |
| the readers: percentiles, the slowest frames, a request with no pass, show.py on a sample session | perf 11, 20, 21; telemetry 27, 28 | the reader tool's own tests, at the build of `run.sh perf` and the replayer |
| the helpers' keys and the vocabulary tables | telemetry 19, 20, 21, 22, 23 | each owning module's tests, at that module's build (section 8.1) |
| the GPU sample, PERF_NONE, the GIL check, the clip rename | perf 10, 17; telemetry 18 | dropped with their mechanism: no GPU record (RCD34 B1), no handle (PRF7), the clip claim unchanged (TEL8) |
| the stall on a dead writer, a stuck write, a slow writer, not when idle; a first record after a long idle | telemetry 11, 12 | recorder test 15 and a new test of `writerStalled` to add at the build: a filled image older than 5 s, and none when the queue is empty |
