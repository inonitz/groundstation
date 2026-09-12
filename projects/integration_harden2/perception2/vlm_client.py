"""llama-server client for the reasoning brain (Qwen3-VL-4B). Sends the current frame + the
detector's findings + the user's question. Returns a spoken-style answer and, when the user asked
to find something, a target phrase plus the VLM's own box guess. Never raises.
Moved verbatim from vlm.py on 2026-09-02; parse_reply() split out of ask() so the text parsing
is testable without a server."""
import base64, json, os, re, subprocess, time, cv2, requests
import config


def _server_up():
    try:
        r = requests.get(config.LLAMA_URL + "/health", timeout=2)
        if r.status_code == 200:
            return True
        if r.status_code == 503:
            return False
        return requests.get(config.LLAMA_URL + "/v1/models", timeout=2).status_code == 200
    except Exception:
        return False


def ensure_server(wait=240):
    """Make sure llama-server is answering config.LLAMA_URL; launch run_llama_server.sh if not, and wait
    for the model to load. Safe against double-launch: if one is already starting (e.g. run_demo's tmux
    pane), just wait instead of spawning a second."""
    if _server_up():
        return True
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "run_llama_server.sh")
    already = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True).returncode == 0
    if not already:
        if not os.path.exists(script):
            print("[vlm] llama-server down and run_llama_server.sh missing:", script, flush=True); return False
        print("[vlm] llama-server not running -> launching it (model load ~30-60s)...", flush=True)
        with open("/tmp/integration_vlm.log", "a") as log:
            subprocess.Popen(["bash", script], stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    else:
        print("[vlm] llama-server is starting; waiting...", flush=True)
    t0 = time.time()
    while time.time() - t0 < wait:
        if _server_up():
            print(f"[vlm] llama-server ready ({time.time()-t0:.0f}s).", flush=True); return True
        time.sleep(2)
    print("[vlm] timed out waiting for llama-server.", flush=True); return False

SYSTEM = (
    "You are a computer-vision system looking through a live camera. Answer the user's question "
    "DIRECTLY about what is actually in THIS image -- objects, people, clothing, colours, text, count, "
    "and where things are. Vary your wording; never repeat a canned description. If something asked about "
    "is not visible, say so plainly. Reply in PLAIN ASCII (straight quotes, no emoji/accents/degree sign).\n"
    "\n"
    "ALWAYS format your reply as EXACTLY these two labelled sections, in this order:\n"
    "LONG RESPONSE: <1-3 sentences, detailed -- this is shown on screen>\n"
    "SHORT RESPONSE: <ONE brief natural sentence -- this is spoken aloud, so be concise; no lists, no rambling>\n"
    "For counting questions (how many / count), BEGIN both responses with the exact integer, e.g. '2 people.'\n"
    "\n"
    "A fast detector also lists objects it found (labels + boxes) as a hint -- use it, but trust your own eyes.\n"
    "ONLY if the user asks to find/point at/highlight a specific thing, add two MORE final lines after the responses:\n"
    "HIGHLIGHT: <a concrete noun phrase a detector can localize, e.g. 'the person in the black hat' or 'red backpack'; or none>\n"
    "VLM_BOX: x1,y1,x2,y2   (normalized 0-1, top-left origin; omit if unsure)"
)


def _b64(frame_bgr):
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode() if ok else ""


def _dets_text(dets):
    if not dets:
        return "(detector found nothing this frame)"
    return "\n".join(f'- {d["label"]} at {list(d["box"])}' for d in dets[:20])


def ask(frame_bgr, question, dets):
    """-> (answer_text, highlight_target|None, vlm_box|None). vlm_box is normalized xyxy."""
    content = [
        {"type": "text",
         "text": f"Detector found:\n{_dets_text(dets)}\n\nUser asks: {question}"},
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + _b64(frame_bgr)}},
    ]
    body = {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": content}],
            "temperature": 0.6, "max_tokens": 256}
    try:
        r = requests.post(config.LLAMA_URL + "/v1/chat/completions", json=body, timeout=config.VLM_TIMEOUT)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return (f"[VLM unavailable: {e}]", None, None, "")
    return parse_reply(txt)


def parse_reply(txt):
    """Split the model's labelled reply into (long, target, box, short). Pure text; testable."""
    target, box = None, None
    m = re.search(r"HIGHLIGHT:\s*(.+)", txt)
    if m:
        t = m.group(1).strip().strip(".")
        target = None if t.lower() in ("none", "n/a", "") else t
    m = re.search(r"VLM_BOX:\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", txt)
    if m:
        box = tuple(float(x) for x in m.groups())
    body = re.split(r"\n?HIGHLIGHT:", txt)[0]
    lm = re.search(r"LONG RESPONSE:\s*(.+?)(?=\n*\s*SHORT RESPONSE:|\Z)", body, re.S | re.I)
    sm = re.search(r"SHORT RESPONSE:\s*(.+)", body, re.S | re.I)
    long_txt = (lm.group(1) if lm else body).strip()
    short_txt = (sm.group(1) if sm else "").strip()
    long_txt = re.sub(r"\b(LONG|SHORT) RESPONSE:\s*", "", long_txt, flags=re.I).strip()  # never leak labels
    if not short_txt:                                            # model gave no short -> first sentence of long
        short_txt = (re.split(r"(?<=[.!?])\s+", long_txt)[0].strip() if long_txt else "")
    long_txt = long_txt or "(no answer)"
    short_txt = re.sub(r"\b(LONG|SHORT) RESPONSE:\s*", "", short_txt, flags=re.I).strip() or long_txt
    return (long_txt, target, box, short_txt)   # (screen_long, highlight_target, box, spoken_short)
