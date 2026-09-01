"""phone_ears.py -- the PHONE as the user's mic for the MVD (inbound command channel).

Matches the app EXACTLY (com/kcg/dr/voice/GroundStationSpeechResolver.kt + utils/TCPClient.kt):
the phone, per spoken command, sends the SAME payload TWO ways to the groundstation:
  1. REST : POST http://<groundstation-ip>:<port>/input   body {"text":"<transcript>"}   (expects 200)
  2. TCP  : a persistent socket to <groundstation-ip>:<port>, one newline-delimited JSON
            line per command:  {"text":"<transcript>"}\\n
BOTH on the SAME port (app default 8080; VoiceControlFragment has `("0.0.0.0", 8080)` with a
fixme to set the address to THIS laptop's IP on the phone hotspot). Because the app fires both
channels every time, we DEDUPE identical text within a short window so a command runs once.

Each received transcript is handed to on_text(text) -- the same handler the local ASR uses
(router -> deterministic drone verbs, else -> perception / Qwen-VL). Pure stdlib asyncio: one
socket server that sniffs HTTP vs raw-line so a single port serves both. Runs in a bg thread.
"""
import asyncio
import json
import threading
import time

_HTTP_METHODS = ("POST", "GET", "PUT", "HEAD", "OPTIONS", "DELETE", "PATCH")


class PhoneEars:
    def __init__(self, on_text, host="0.0.0.0", port=8080, dedup_window=1.5):
        self._on_text = on_text
        self.host = host
        self.port = port
        self._dedup_window = dedup_window
        self._last = ("", 0.0)
        self._loop = None
        self._server = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _extract(self, raw):
        raw = (raw or "").strip()
        if raw.startswith("{"):
            try:
                return str(json.loads(raw).get("text", "")).strip()
            except Exception:
                return raw
        return raw

    def _feed(self, text):
        text = (text or "").strip()
        if not text:
            return
        now = time.monotonic()
        if text == self._last[0] and (now - self._last[1]) < self._dedup_window:
            return                                  # app sends each command via BOTH REST and TCP
        self._last = (text, now)
        try:
            self._on_text(text)
        except Exception as e:
            print("[phone_ears] on_text err:", e, flush=True)

    async def _handle(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            first = await reader.readline()
            if not first:
                writer.close(); return
            line = first.decode("utf-8", "replace").rstrip("\r\n")

            if any(line.startswith(m + " ") for m in _HTTP_METHODS):
                # --- HTTP request (the REST /input path) ---
                headers = {}
                while True:
                    h = await reader.readline()
                    if h in (b"\r\n", b"\n", b""):
                        break
                    k, _, v = h.decode("utf-8", "replace").partition(":")
                    headers[k.strip().lower()] = v.strip()
                clen = int(headers.get("content-length", "0") or 0)
                body = (await reader.readexactly(clen)).decode("utf-8", "replace") if clen else ""
                self._feed(self._extract(body))
                payload = b'{"ok": true}'
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload
                )
                await writer.drain()
                writer.close()
            else:
                # --- raw TCP, newline-delimited JSON lines (persistent) ---
                print(f"[phone_ears] TCP client {peer} connected", flush=True)
                self._feed(self._extract(line), "TCP")
                while True:
                    l = await reader.readline()
                    if not l:
                        break
                    self._feed(self._extract(l.decode("utf-8", "replace").rstrip("\r\n")), "TCP")
                print(f"[phone_ears] TCP client {peer} disconnected", flush=True)
                writer.close()
        except Exception as e:
            print("[phone_ears] conn err:", e, flush=True)
            try: writer.close()
            except Exception: pass

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            coro = asyncio.start_server(self._handle, self.host, self.port)
            self._server = self._loop.run_until_complete(coro)
        except Exception as e:
            print(f"[phone_ears] could not bind {self.host}:{self.port} -> {e}", flush=True)
            return
        print(f"[phone_ears] listening on {self.host}:{self.port} "
              f"(REST POST /input + raw TCP JSON lines) -- phone ASR channel", flush=True)
        self._loop.run_forever()

    def shutdown(self):
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
