"""Entry point: wire the existing ASR (ROS2 asr_node -> Ears) into the Router.

  python3 -m source.integration.run_router                 # mock at 127.0.0.1:8080
  python3 -m source.integration.run_router --host <phone-ip> --real   # HUMAN-run only

Basic verbs fly the drone (deterministic); complex transcripts go to the perception
engine via on_complex. Press H in the asr_node terminal to talk (push-to-talk).
"""
import argparse

try:
    from .dji_wire import DjiWire
    from .router import Router
except ImportError:
    from dji_wire import DjiWire
    from router import Router


def _make_perception_handler():
    """Return an on_complex(text) callback. We import perception lazily so the router +
    wire can be tested without ROS/torch present. Falls back to a print if unavailable."""
    try:
        # scene_omdet.py is the real app and wires perception directly.
        # This standalone router harness has no perception engine -> degrade to logging.
        raise ImportError("standalone router harness: no perception engine wired")
    except Exception as e:  # perception not importable in this env -- degrade gracefully
        print(f"[router] perception engine not wired ({e}); complex cmds will be logged only")
        return lambda text: print(f"[router] COMPLEX (no perception): {text!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--real", action="store_true",
                    help="allow a non-loopback host (real drone). HUMAN-run only.")
    args = ap.parse_args()

    wire = DjiWire(host=args.host, port=args.port, allow_real=args.real)
    router = Router(wire, on_complex=_make_perception_handler())

    from ears import Ears  # ROS2 subscriber to /asr_server/transcribe

    def on_text(text):
        r = router.handle(text)
        print(f"[router] {text!r} -> {r.tier.value}/{r.action} (dispatched={r.dispatched})")

    ears = Ears(on_text)
    print(f"[router] listening. host={args.host}:{args.port} real={args.real}. Ctrl-C to quit.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ears.shutdown()


if __name__ == "__main__":
    main()
