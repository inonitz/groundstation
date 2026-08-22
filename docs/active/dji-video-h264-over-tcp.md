# Raw H.264/H.265 off the DJI drone, over one TCP socket

You hit a wall because `LiveStreamManager` only speaks RTMP, RTSP, GB28181, and Agora.
That is the wrong API for us. There is a second one that hands you the raw encoded
frames directly, with no protocol and no media server. This is the one to use.

## Verify this first

Read these before the code. They are the proof, not my word.

1. **DJI's own API reference** — [`ICameraStreamManager`](https://developer.dji.com/api-reference-v5/android-api/Components/IMediaDataCenter/ICameraStreamManager.html).
   It documents `addReceiveStreamListener`. DJI's words: the listener lets you "receive the
   **raw video stream data** of the specified camera. You can use this stream data to
   **decode and display it yourself**." It is separate from `LiveStreamManager`.
2. **It is already in your repo** — [`CameraStreamDetailVM.kt`](https://github.com/ExoSkeletons/DJI-android-sdk-v5-recon-swarm/blob/main/SampleCode-V5/android-sdk-v5-sample/src/main/java/dji/sampleV5/aircraft/models/CameraStreamDetailVM.kt).
   The listener is at **L66**. It writes the raw bytes to a file at **L76**
   (`streamFileOutputStream?.write(data, offset, length)`). It registers the listener at **L242**.
   That sample already does 90% of the work — it just saves to disk instead of a socket.
3. **Official DJI sample repo** — [dji-sdk/Mobile-SDK-Android-V5](https://github.com/dji-sdk/Mobile-SDK-Android-V5).
   Same file, upstream.
4. **Other people doing exactly this** — [Issue #404: Capture frame with CameraStreamManager](https://github.com/dji-sdk/Mobile-SDK-Android-V5/issues/404),
   and for our aircraft, [Issue #566: camera stream on Mini 4 Pro](https://github.com/dji-sdk/Mobile-SDK-Android-V5/issues/566).

## The idea

DJI gives you the video already compressed as H.264 or H.265. You do not transcode it.
You write those exact bytes to a TCP socket. Linux connects to that socket and decodes.
No RTMP. No ingest server. Latency is roughly 150–300 ms plus the LAN, well under our 1 s budget.

## Android: forward the raw stream to a socket

New file, `flight/dji/VideoTcpStreamer.kt`. The phone opens a plain TCP server. Linux dials in.
Every callback's bytes go straight to that client.

```kotlin
package com.kcg.dr.flight.dji

import android.util.Log
import dji.sdk.keyvalue.value.common.ComponentIndexType
import dji.v5.manager.datacenter.MediaDataCenter
import dji.v5.manager.interfaces.ICameraStreamManager
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/**
 * Forwards the drone's raw H.264/H.265 stream to a TCP client (the Linux box).
 *
 * DJI hands us the already-encoded video through ICameraStreamManager. We do not
 * transcode or wrap it -- we write the exact bytes to a socket. Linux decodes.
 */
class VideoTcpStreamer(
    // Use the same camera index the app already renders (the main camera on a Mini).
    private val cameraIndex: ComponentIndexType = ComponentIndexType.LEFT_OR_MAIN,
    private val port: Int = 5600,
) {
    private val cameraManager get() = MediaDataCenter.getInstance().cameraStreamManager

    // The connected Linux client. Set on the accept thread, read on DJI's callback thread.
    private val client = AtomicReference<Socket?>(null)
    private val loggedCodec = AtomicBoolean(false)

    private var serverSocket: ServerSocket? = null
    private val acceptPool = Executors.newSingleThreadExecutor()

    // DJI calls this for every encoded chunk. We forward it verbatim.
    private val streamListener = ICameraStreamManager.ReceiveStreamListener { data, offset, length, info ->
        // Log the codec once so the Linux side picks h264parse vs h265parse.
        if (loggedCodec.compareAndSet(false, true)) Log.i(TAG, "video codec = ${info.mimeType}")

        val sink = client.get() ?: return@ReceiveStreamListener   // nobody connected yet
        try {
            // Write here, on the callback thread, before DJI reuses `data`.
            sink.getOutputStream().write(data, offset, length)
        } catch (e: Exception) {
            // Client went away. Drop it; the accept loop takes the next one.
            client.compareAndSet(sink, null)
            runCatching { sink.close() }
        }
    }

    fun start() {
        val server = ServerSocket(port)
        serverSocket = server
        cameraManager.addReceiveStreamListener(cameraIndex, streamListener)

        acceptPool.execute {
            while (!server.isClosed) {
                val next = runCatching { server.accept() }.getOrNull() ?: break
                next.tcpNoDelay = true   // low latency: send each chunk immediately
                // One client at a time. Replace and close any previous one.
                client.getAndSet(next)?.let { runCatching { it.close() } }
                Log.i(TAG, "video client connected: ${next.inetAddress}")
            }
        }
    }

    fun stop() {
        cameraManager.removeReceiveStreamListener(streamListener)
        client.getAndSet(null)?.let { runCatching { it.close() } }
        runCatching { serverSocket?.close() }
        acceptPool.shutdownNow()
    }

    private companion object {
        const val TAG = "VideoTcpStreamer"
    }
}
```

Wire it next to your existing `/c/stream` routes in `ApiServer.kt`. Keep one instance, and
**respond** so the client can confirm the call landed:

```kotlin
private val video = VideoTcpStreamer()

route("/video") {
    post("/start") { video.start(); call.respond(ok { put("port", 5600) }) }
    post("/stop")  { video.stop();  call.respond(ok()) }
}
```

## Linux: read and decode

GStreamer reads the socket and decodes. This one line lets you eyeball it live:

```bash
gst-launch-1.0 tcpclientsrc host=<phone-ip> port=5600 ! h265parse ! avdec_h265 ! videoconvert ! autovideosink
```

Swap `h265` for `h264` if the codec log says H.264. Our real code feeds this into perception
through an `appsink` — that part is on us.

## Confirm two things on the phone

- **Codec.** The `video codec = ...` log line tells us H.264 or H.265. Mini 4 Pro is often H.265.
- **Resolution and frame rate.** `StreamInfo` carries them. Send us whatever it reports.

That is the whole change. The sample already grabs the raw stream — you are only redirecting
those bytes from a file to a socket.

## CONFIRMED on real hardware (2026-08-22)
- **Live feed decodes end-to-end** over the phone hotspot: real DJI camera → raw H.264 TCP on `:5600`
  → OpenCV+GStreamer (`tcpclientsrc ! h264parse ! avdec_h264 ! appsink`) → 60 frames read clean.
- **Codec:** H.264 (Annex-B byte-stream; NAL types 7=SPS, 8=PPS, 5=IDR, 1=slice present).
- **Resolution:** 1920×1080.  **Frame rate:** ~24.4 fps.  **Bitrate:** ~740 kbps (observed 5 s window).
- **Transport:** works over the hotspot WiFi (NOT blocked). The phone IP is the hotspot gateway and
  changes on reboot — derive it: `ip route show dev wlp2s0 | awk '/^default/{print $3}'`.
- No app rebuild, no port change, no muxing needed. `VideoTcpServer` auto-starts on `:5600`
  via `ApiServerService`.

## MEASURED end-to-end latency (2026-08-22, `measure_video_e2e.py`)
Flash-to-perception (monitor → drone camera → RC/RF → WiFi → phone → rx_node decode → ROS → consumer),
automatic flash-detection, n>100:
- **p50 ≈ 320 ms** (steady bulk 270–360 ms). Jitter spikes to 500–1100 ms (WiFi retransmit + 10 s GOP recovery).
- Breakdown: DJI air-link + encode ≈ 200–250 ms (OcuSync/MSDK floor, NOT reducible from our side);
  receiver decode + ROS < 30 ms (already optimized: explicit H.264, no decodebin, no frame-threading).
- **Implication:** do NOT use this pipeline for close-range collision avoidance (320 ms + ~150 ms depth ≈
  0.5 s to decide, ~1 s worst case). Use the aircraft's ONBOARD obstacle avoidance for collision; reserve
  this pipeline for higher-level perception where ~0.3 s is tolerable.
