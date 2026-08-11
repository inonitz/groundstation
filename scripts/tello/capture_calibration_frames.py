#!/usr/bin/env python3
"""Grab checkerboard frames from a real Tello for B2 camera calibration.
Standalone -- no ROS2/FMU build needed. Connect to the Tello's WiFi first,
then: python3 capture_calibration_frames.py [out_dir] [board_cols] [board_rows]
Press SPACE to save a frame, ESC to quit. Aim for 20-40 frames, varied angle/distance."""
import sys, os, time, socket, threading, subprocess
import cv2

TELLO_CMD_ADDR = ("192.168.10.1", 8889)
TELLO_BIND_ADDR = ("0.0.0.0", 8889)
VIDEO_PORT = 11111
STATE_PORT = 8890
STREAM_URL = f"udp://0.0.0.0:{VIDEO_PORT}"

# Same source stage rx_node.cpp uses under --tello: the Tello sends raw H.264 with no RTP
# framing, so h264parse handles the NAL units and there is no depay stage. FFMPEG's UDP
# demuxer has to guess the format from a probe and gives up on a slow first keyframe, so
# GStreamer is tried first and FFMPEG is only the fallback.
GST_PIPELINE = (f"udpsrc port={VIDEO_PORT} ! h264parse ! avdec_h264 ! videoconvert ! "
                "video/x-raw, format=BGR ! appsink max-buffers=1 drop=true sync=false")

# The Tello leaves SDK mode if it hears nothing for 15s -- it beeps, goes red, and
# lands if airborne. A silent capture loop always trips this, so a background thread
# re-sends "command" well inside that window for the whole session.
KEEPALIVE_PERIOD_S = 5.0

# Detect on a half-size image. The preview overlay does not need full-res corners, and the
# cost scales far worse than linearly: on a frame with no clean board, the search runs ~16ms
# at 480x360 against ~84ms at 960x720. calibrate_camera.py still works at full resolution,
# where accuracy actually matters.
DETECT_SCALE = 0.5


def send_and_wait(sock, msg, timeout_s):
	"""Send an SDK command and return the drone's reply, or None if it stayed silent."""
	sock.settimeout(timeout_s)
	sock.sendto(msg.encode(), TELLO_CMD_ADDR)
	try:
		reply, _ = sock.recvfrom(1024)
	except socket.timeout:
		return None
	return reply.decode(errors="replace").strip()


def keepalive_loop(sock, stop_event):
	"""Hold SDK mode open until the capture session ends."""
	while not stop_event.wait(KEEPALIVE_PERIOD_S):
		try:
			sock.sendto(b"command", TELLO_CMD_ADDR)
		except OSError as e:
			print(f"keepalive send failed: {e}")
	return


def state_loop(stop_event, battery):
	"""Track live battery %% from the Tello state broadcast on UDP 8890.

	The drone broadcasts semicolon-separated state (`...;bat:87;...`) once in SDK mode.
	This is passive: it only reads, so it never competes with the video keepalive."""
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	try:
		sock.bind(("0.0.0.0", STATE_PORT))
	except OSError as e:
		print(f"battery monitor off: could not bind UDP {STATE_PORT}: {e}")
		return
	sock.settimeout(1.0)
	while not stop_event.is_set():
		try:
			data, _ = sock.recvfrom(1024)
		except socket.timeout:
			continue
		except OSError:
			break
		for kv in data.decode(errors="replace").split(";"):
			if kv.startswith("bat:"):
				battery[0] = kv[4:].strip()
	sock.close()
	return


def wait_for_video_packets(timeout_s):
	"""Confirm the drone is actually sending video before any decoder opens.

	streamon returning ok only means the command was accepted. Opening a decoder against
	a silent port fails in a way that looks identical to a broken WiFi link, so check the
	wire first and separate the two cases."""
	probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	probe.settimeout(timeout_s)
	got = False
	try:
		probe.bind(("0.0.0.0", VIDEO_PORT))
		probe.recvfrom(4096)
		got = True
	except socket.timeout:
		pass
	except OSError as e:
		print(f"could not bind UDP {VIDEO_PORT}: {e} -- another process already holds it.")
	finally:
		probe.close()
	return got


def firewall_hint():
	"""The drone's video is unsolicited inbound, so a default-deny INPUT policy eats it.

	The command socket is unaffected: it sends first, so conntrack sees the replies as an
	established flow and lets them back in. That asymmetry makes a firewall look like a
	video bug -- handshake fine, stream silent. devenv.sh inserts these rules at container
	startup, so a missing rule means this container was not launched through it. Checked
	with iptables, not ufw: ufw reports success in this image without applying anything
	(docs/ARCHITECTURE.md section 17)."""
	missing = []
	for port in (VIDEO_PORT, STATE_PORT):
		try:
			r = subprocess.run(["iptables", "-C", "INPUT", "-p", "udp", "--dport", str(port),
			                    "-j", "ACCEPT"], capture_output=True, timeout=5)
		except (OSError, subprocess.SubprocessError):
			return ""
		if r.returncode != 0:
			missing.append(port)
	if not missing:
		return ""
	rules = "\n".join(f"    iptables -I INPUT 1 -p udp --dport {p} -j ACCEPT" for p in missing)
	return ("\n  The netfilter ACCEPT rule is MISSING for UDP " +
	        ", ".join(str(p) for p in missing) + ".\n"
	        "  devenv.sh adds these at container startup, so this container was launched\n"
	        "  without it. Insert them by hand, as root inside the container, no sudo:\n"
	        + rules + "\n"
	        "  Do not use ufw here -- it reports success without applying the rule.\n"
	        "  See docs/ARCHITECTURE.md section 17.")


def open_stream():
	"""Open the video stream, GStreamer first, FFMPEG second. Returns (cap, backend)."""
	cap = cv2.VideoCapture(GST_PIPELINE, cv2.CAP_GSTREAMER)
	if cap.isOpened():
		return cap, "GStreamer"
	cap.release()
	print("GStreamer pipeline did not open, falling back to FFMPEG")
	cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
	if cap.isOpened():
		cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
		return cap, "FFMPEG"
	cap.release()
	return None, None


def read_first_frame(cap, timeout_s):
	"""Retry the first read until a keyframe lands. A cold decoder drops the first reads."""
	deadline = time.time() + timeout_s
	while time.time() < deadline:
		ok, frame = cap.read()
		if ok and frame is not None:
			return frame
		time.sleep(0.1)
	return None


def main():
	out_dir = sys.argv[1] if len(sys.argv) > 1 else "calib_frames"
	board_cols = int(sys.argv[2]) if len(sys.argv) > 2 else 9
	board_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 6
	os.makedirs(out_dir, exist_ok=True)

	# Bind 8889 locally: the Tello replies to that port, and without the bind the
	# replies land on an ephemeral port we never read, so the handshake looks silent.
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	sock.bind(TELLO_BIND_ADDR)

	reply = send_and_wait(sock, "command", 5.0)
	if reply is None:
		print("ERROR: no reply to 'command' -- laptop is not on the Tello's WiFi, "
		      "or something else already holds UDP 8889.")
		sys.exit(1)
	if reply.lower() != "ok":
		print(f"ERROR: Tello refused SDK mode, replied '{reply}'.")
		sys.exit(1)
	print("SDK mode entered (drone replied ok)")

	stop_event = threading.Event()
	keepalive = threading.Thread(target=keepalive_loop, args=(sock, stop_event), daemon=True)
	keepalive.start()
	battery = [None]
	state = threading.Thread(target=state_loop, args=(stop_event, battery), daemon=True)
	state.start()

	reply = send_and_wait(sock, "streamon", 5.0)
	if reply is None or reply.lower() != "ok":
		print(f"ERROR: 'streamon' not accepted (replied {reply!r}).")
		stop_event.set()
		sys.exit(1)
	print(f"streamon accepted -- waiting for video packets on UDP {VIDEO_PORT}")

	if not wait_for_video_packets(10.0):
		print(f"ERROR: no video packets on UDP {VIDEO_PORT} after 10s, though streamon "
		      "was accepted. The drone thinks it is streaming, so the packets are being "
		      "dropped before they reach this process." + firewall_hint())
		stop_event.set()
		sys.exit(1)
	print("video packets arriving -- opening decoder")

	cap, backend = open_stream()
	if cap is None:
		print("ERROR: video packets are arriving but no decoder would open. Neither the "
		      "GStreamer nor the FFMPEG backend accepted the stream.")
		stop_event.set()
		sys.exit(1)
	print(f"decoder open via {backend}")

	frame = read_first_frame(cap, 10.0)
	if frame is None:
		print("ERROR: decoder opened but produced no frame in 10s -- no keyframe decoded.")
		stop_event.set()
		cap.release()
		sys.exit(1)
	h, w = frame.shape[:2]
	print(f"CONFIRMED resolution: {w}x{h} -- use this for cols/rows below, not an assumed value.")

	# Continue numbering from frames already in out_dir. The real Tello overheats and
	# powers off after a few minutes on a table (props still, no cooling airflow), so a
	# full 20-40 frame set is captured in short bursts with cool-downs between. Resetting
	# to 0 each run would overwrite the earlier burst, so resume past the highest index.
	existing = [f for f in os.listdir(out_dir)
	            if f.startswith("frame_") and f.endswith(".png") and f[6:-4].isdigit()]
	saved = max((int(f[6:-4]) for f in existing), default=-1) + 1
	if saved:
		print(f"resuming at frame_{saved:03d} ({saved} frames already in {out_dir}/)")
	t_start = time.time()
	frame_count = 0
	while True:
		ok, frame = cap.read()
		if not ok:
			continue
		frame_count += 1
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		small = cv2.resize(gray, None, fx=DETECT_SCALE, fy=DETECT_SCALE,
		                   interpolation=cv2.INTER_AREA)
		found, corners = cv2.findChessboardCornersSB(small, (board_cols, board_rows))
		disp = frame.copy()
		if found:
			cv2.drawChessboardCorners(disp, (board_cols, board_rows),
			                          corners / DETECT_SCALE, found)
		live_fps = frame_count / max(time.time() - t_start, 1e-6)
		bat = battery[0]
		bat_ok = bat is not None and bat.isdigit() and int(bat) >= 20
		bat_s = f"bat={bat}%" if bat is not None else "bat=?"
		color = (0, 255, 0) if bat_ok else (0, 0, 255)
		cv2.putText(disp, f"saved={saved}  {live_fps:4.1f} fps  {bat_s}  SPACE=save  ESC=quit", (10, 30),
		            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
		cv2.imshow("Tello calibration capture", disp)
		key = cv2.waitKey(1) & 0xFF
		if key == 27:
			break
		if key == 32:
			path = os.path.join(out_dir, f"frame_{saved:03d}.png")
			cv2.imwrite(path, frame)
			print(f"saved {path} (checkerboard {'found' if found else 'NOT found'})")
			saved += 1

	elapsed = time.time() - t_start
	print(f"measured stream fps ~= {frame_count / elapsed:.1f} over {elapsed:.1f}s -- use this in the YAML, not an assumed 30.0")
	print(f"saved {saved} frames to {out_dir}/ (target 20-40)")

	stop_event.set()
	cap.release()
	cv2.destroyAllWindows()
	sock.sendto(b"streamoff", TELLO_CMD_ADDR)
	sock.close()
	return


if __name__ == "__main__":
	main()
