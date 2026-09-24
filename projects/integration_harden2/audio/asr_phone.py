"""Speech in from the PHONE: the phone app sends each transcript to the laptop.

Matches the app EXACTLY (com/kcg/dr/voice/GroundStationSpeechResolver.kt +
utils/TCPClient.kt): the phone, per spoken command, sends the SAME payload TWO ways to
the groundstation: 1. REST : POST http://<groundstation-ip>:<port>/input body
{"text":"<transcript>"}   (expects 200) 2. TCP  : a persistent socket to
<groundstation-ip>:<port>, one newline-delimited JSON line per command:
{"text":"<transcript>"}\n BOTH on the SAME port (app default 8080; VoiceControlFragment
has `("0.0.0.0", 8080)` with a fixme to set the address to THIS laptop's IP on the phone
hotspot). Because the app fires both channels every time, we DEDUPE identical text within
a short window so a command runs once.

Each received transcript is handed to on_heard(text, "phone") -- the same handler the
laptop mic uses (the recognizer). Pure stdlib asyncio: one socket server that sniffs HTTP
vs raw-line so a single port serves both. Runs in a bg thread.

Phone input is untrusted network data: a dropped connection, a short body or a line over
the stream limit ends that ONE connection (util.guarded.stream_call), never the app.
"""
import asyncio
import concurrent.futures
import queue
import threading
import time

import config
from system.fatal import asyncio_crash_handler
from system.status import DOWN, UP, Status, fail
from util.guarded import parse_json, stream_call
from util.net import port_open

_HTTP_METHODS = ("POST", "GET", "PUT", "HEAD", "OPTIONS", "DELETE", "PATCH")


class PhoneAsr:
    """@on_heard(text, "phone"). Owns the "phone speech" status row (status())."""

    def __init__(
        self,
        on_heard,
        host="0.0.0.0",
        port=None,
        dedup_window=1.5,
    ):
        self._on_heard = on_heard
        self.host = host
        self.port = port or config.PHONE_ASR_PORT   # read when built, not imported
        self._dedup_window = dedup_window
        self._last = ("", 0.0)
        self._loop = None
        self._server = None
        self._status = Status("phone speech")
        # Transcripts go to the app on ONE delivery thread, never inside the asyncio
        # loop: a command can plan for seconds (Gemma), and a blocked loop read the
        # duplicate REST/TCP copy after the dedup window and flew the mission TWICE
        # (review R21). The queue keeps the order; get() blocks, no poll.
        self._inbox = queue.Queue()
        self._deliverer = threading.Thread(
            target=self._deliver,
            name="phone-speech-deliver",
            daemon=True,
        )
        self._deliverer.start()
        self._listening = threading.Event()     # set once the server is bound
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return

    def status(self):
        """[(name, state, detail)]: the "phone speech" row."""
        return [self._status.row()]

    def _extract(self, raw):
        """Pull the transcript from a payload: a {'text': ...} JSON line, or the raw
        text itself. Phone input is untrusted network data: a garbled line is dropped
        with a log line and returns "" (so _feed skips it). It must not end the
        connection or the app (review finding R7)."""
        raw = (raw or "").strip()
        if not raw.startswith("{"):
            return raw

        ok, obj = parse_json(raw)
        if not ok:
            print(f"[asr_phone] dropped a bad line ({obj}): {raw[:80]!r}", flush=True)
            return ""
        if not isinstance(obj, dict):
            return ""
        return str(obj.get("text", "")).strip()

    def _feed(self, text):
        """Dedup at RECEIPT, then queue the transcript for the delivery thread. Runs
        on the asyncio loop and returns at once, so the loop reads the phone's second
        copy immediately and the dedup catches it."""
        text = (text or "").strip()
        if not text:
            return

        now = time.monotonic()
        if text == self._last[0] and (now - self._last[1]) < self._dedup_window:
            # the app sends each command via BOTH REST and TCP
            return
        self._last = (text, now)
        self._inbox.put(text)
        return

    def _deliver(self):
        """The one consumer: hand each transcript to the app, in order. None = stop."""
        text = None

        while True:
            text = self._inbox.get()
            if text is None:
                return
            self._on_heard(text, "phone")

    @staticmethod
    async def _readline(reader):
        """One line, or b"" when the connection is unusable (the phone left, or a line
        over the 64 KiB stream limit). b"" ends that ONE connection like a normal close
        (review R7, R12)."""
        ok, line = await stream_call(reader.readline())
        if not ok:
            print(f"[asr_phone] connection ended: {line}", flush=True)
            return b""
        return line

    async def _handle(self, reader, writer):
        peer = writer.get_extra_info("peername")
        first = await self._readline(reader)
        if not first:
            writer.close()
            return

        line = first.decode("utf-8", "replace").rstrip("\r\n")
        if any(line.startswith(m + " ") for m in _HTTP_METHODS):
            await self._handle_http(reader, writer)
            return
        await self._handle_tcp(reader, writer, peer, line)
        return

    async def _handle_http(self, reader, writer):
        """The REST /input path: read the headers and body, feed the transcript,
        answer 200."""
        header = b""
        raw = b""
        headers = {}
        body = ""
        payload = b'{"ok": true}'

        while True:
            header = await self._readline(reader)
            if header in (b"\r\n", b"\n", b""):
                break
            key, _, value = header.decode("utf-8", "replace").partition(":")
            headers[key.strip().lower()] = value.strip()

        # a bad Content-Length header reads as no body
        declared = headers.get("content-length", "0")
        length = int(declared) if declared.isdigit() else 0
        if length:
            ok, raw = await stream_call(reader.readexactly(length))
            if not ok:
                print(f"[asr_phone] short HTTP body, connection ended: {raw}",
                      flush=True)
                writer.close()
                return
            body = raw.decode("utf-8", "replace")
        self._feed(self._extract(body))

        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: "
            + str(len(payload)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + payload
        )
        ok, error = await stream_call(writer.drain())
        if not ok:                          # the phone left before our 200 was written
            print(f"[asr_phone] reply not delivered: {error}", flush=True)
        writer.close()
        return

    async def _handle_tcp(self, reader, writer, peer, first_line):
        """The raw TCP path: newline-delimited JSON lines on a persistent socket."""
        line = b""

        print(f"[asr_phone] TCP client {peer} connected", flush=True)
        self._feed(self._extract(first_line))
        while True:
            line = await self._readline(reader)
            if not line:
                break
            self._feed(self._extract(line.decode("utf-8", "replace").rstrip("\r\n")))
        print(f"[asr_phone] TCP client {peer} disconnected", flush=True)
        writer.close()
        return

    def _run(self):
        # A taken port is a misconfiguration: FAILED row, then die with the reason. The
        # check replaces a catch around the bind; a port taken in the instant after the
        # check makes the bind throw, and the crash hook dies with that error.
        if port_open("127.0.0.1", self.port):
            fail(
                self._status,
                f"port {self.port} is taken",
                f"phone ASR cannot bind {self.host}:{self.port}: another program "
                "already listens on that port",
            )

        self._loop = asyncio.new_event_loop()
        # an escaped handler error is a bug -> die
        self._loop.set_exception_handler(asyncio_crash_handler)
        asyncio.set_event_loop(self._loop)
        coro = asyncio.start_server(self._handle, self.host, self.port)
        self._server = self._loop.run_until_complete(coro)

        self._status.set(UP)
        print(
            f"[asr_phone] listening on {self.host}:{self.port} "
            "(REST POST /input + raw TCP JSON lines) -- phone ASR channel",
            flush=True
        )
        self._listening.set()
        self._loop.run_forever()
        self._loop.close()
        return

    def close(self):
        """Stop cleanly: close the server, cancel every connection handler and wait for
        them, then stop the loop. A handler still pending when its loop goes away is an
        asyncio error ("Task was destroyed but it is pending"), and the crash handler
        would kill the app for it."""
        self._inbox.put(None)               # the delivery thread ends
        self._listening.wait()
        done = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        finished, _ = concurrent.futures.wait([done], timeout=5.0)
        if not finished:
            print("[asr_phone] the listener did not stop within 5 s", flush=True)

        self._thread.join(timeout=5.0)
        self._deliverer.join(timeout=5.0)
        self._status.set(DOWN)
        return

    async def _shutdown(self):
        self._server.close()
        handlers = [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]
        for task in handlers:
            task.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)   # the cancellations
        self._loop.stop()
        return
