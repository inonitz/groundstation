#!/usr/bin/env python3
"""
S1 SDK PROBE -- the 10-second "is this robot usable" test.

Opens the plaintext-SDK control port and sends `command;`. If the robot replies
`ok;`, SDK mode is ENABLED -- either it's an EP, or this S1 was already unlocked
by the seller (jackpot: no hack needed). If the port refuses or times out, SDK
mode is LOCKED -> the S1 needs the community root/unlock (see README.md).

Stdlib only. No deps. Read-only: sends `command;` and `version;`, nothing that moves.

Usage:
  python3 s1_probe.py                 # AP/direct mode  -> 192.168.2.1
  python3 s1_probe.py 192.168.42.2    # USB/RNDIS mode
  python3 s1_probe.py <ip>            # router/station mode (find ip via broadcast, see README)
"""
import socket, sys

CTRL_PORT = 40923
ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.2.1"

def send(sock, cmd, t=3.0):
    sock.settimeout(t)
    sock.sendall((cmd.strip() + ";").encode())
    try:
        return sock.recv(1024).decode(errors="replace").strip()
    except socket.timeout:
        return "<timeout>"

print(f"[probe] connecting {ip}:{CTRL_PORT} ...")
try:
    s = socket.create_connection((ip, CTRL_PORT), timeout=5)
except Exception as e:
    print(f"[probe] CONNECT FAILED: {e}")
    print("[probe] VERDICT: SDK port not reachable -> either wrong Wi-Fi/IP, or SDK is LOCKED.")
    print("        If you ARE on the robot's Wi-Fi and this fails, the S1 needs the unlock (README.md).")
    sys.exit(2)

with s:
    r = send(s, "command")
    print(f"[probe] command; -> {r!r}")
    if r.startswith("ok"):
        v = send(s, "version")
        print(f"[probe] version; -> {v!r}")
        send(s, "quit")
        print("[probe] VERDICT: *** SDK MODE ENABLED *** -- text API works. No hack needed.")
        sys.exit(0)
    else:
        print("[probe] VERDICT: connected but no 'ok;' -> SDK not in a usable state.")
        sys.exit(3)
