#!/usr/bin/env python3
"""
Mock of the recon-swarm VideoTcpServer (com/kcg/dr/api/VideoTcpServer.kt), so the Linux
DJI video consumer can be built and tested with NO drone and NO Android device.

Faithful to the real transport: a plain TCP server on DEFAULT_STREAM_PORT (5600). It accepts
ONE client at a time and writes a raw H.264/H.265 elementary stream (Annex-B NAL units) with
NO framing header -- exactly what the app's ReceiveStreamListener does
(out.write(data, offset, length)). The clip is looped and paced to ~real time.

Make a clip first (raw Annex-B, matching what DJI emits):
  gst-launch-1.0 videotestsrc num-buffers=150 ! video/x-raw,width=640,height=360,framerate=30/1 \
    ! x264enc tune=zerolatency key-int-max=30 ! h264parse \
    ! 'video/x-h264,stream-format=byte-stream,alignment=au' ! filesink location=clip.h264
  (use x265enc + h265parse + 'video/x-h265,stream-format=byte-stream' for an H.265 clip.)
  NOTE: the byte-stream caps are REQUIRED -- without them gst writes AVC (length-prefixed),
  which h264parse cannot preroll on read (the decoder hangs). DJI emits Annex-B byte-stream.

Run:  python3 video_tcp_mock.py [port=5600] [clip=clip.h264] [clip_seconds=5.0]
Then point the consumer at tcp://127.0.0.1:5600.
"""
import socket
import sys
import time


def serve(port: int, clip_path: str, clip_seconds: float):
    with open(clip_path, "rb") as f:
        data = f.read()
    rate = max(1.0, len(data) / clip_seconds)   # bytes/sec, to pace ~real time
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    print(f"[video-mock] serving {clip_path} ({len(data)} bytes) on 0.0.0.0:{port} "
          f"(~{rate/1024:.0f} KiB/s, loop)", flush=True)

    while True:
        conn, addr = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[video-mock] client connected: {addr}", flush=True)
        loops = 0
        try:
            while True:                          # loop the clip forever, like a live feed
                sent, t0 = 0, time.monotonic()
                while sent < len(data):
                    chunk = data[sent:sent + 4096]
                    conn.sendall(chunk)
                    sent += len(chunk)
                    expected = sent / rate       # pace to the clip's real-time bitrate
                    elapsed = time.monotonic() - t0
                    if expected > elapsed:
                        time.sleep(expected - elapsed)
                loops += 1
        except (BrokenPipeError, ConnectionResetError):
            print(f"[video-mock] client gone after {loops} loop(s)", flush=True)
        finally:
            conn.close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5600
    clip = sys.argv[2] if len(sys.argv) > 2 else "clip.h264"
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    serve(port, clip, secs)
