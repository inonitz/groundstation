"""llama-server client for the reasoning brain (Qwen3-VL-4B). Sends the current frame + the
detector's findings + the user's question. Returns a spoken-style answer and, when the user asked
to find something, a target phrase plus the VLM's own box guess. Never raises."""
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
        with open("/tmp/llm_cv_scene_vlm.log", "a") as log:
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
    "You are a visual assistant looking through a live camera. Answer the user's question "
    "DIRECTLY and specifically about what is actually in THIS image -- the objects, people, "
    "clothing, colours, text, count, and where things are. Vary your wording each time; never "
    "repeat a canned description. 1-3 sentences unless asked for more. If something asked about "
    "is not visible, say so plainly. For counting questions (how many / how much / count), BEGIN the reply with the exact integer, e.g. '2 people.' then at most one short clarifying clause.\n"
    "A fast detector also lists objects it found (labels + boxes) as a hint -- use it, but trust "
    "your own eyes over it.\n"
    "ONLY if the user asks to find/point at/highlight a specific thing, append two final lines:\n"
    "HIGHLIGHT: <a concrete noun phrase a detector can localize; resolve pronouns/descriptions, e.g. 'the person in the black hat' or 'red backpack'; or none>\n"
    "VLM_BOX: x1,y1,x2,y2   (normalized 0-1, top-left origin; omit if unsure)\n"
    "Reply in PLAIN ASCII only (straight quotes, no emoji/accents/degree sign)."
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
        return (f"[VLM unavailable: {e}]", None, None)

    target, box = None, None
    m = re.search(r"HIGHLIGHT:\s*(.+)", txt)
    if m:
        t = m.group(1).strip().strip(".")
        target = None if t.lower() in ("none", "n/a", "") else t
    m = re.search(r"VLM_BOX:\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", txt)
    if m:
        box = tuple(float(x) for x in m.groups())
    answer = re.split(r"\n?HIGHLIGHT:", txt)[0].strip()
    return (answer or "(no answer)", target, box)


def _scale_objects(objs, w, h):
    """Map model boxes (0-1000 normalized, per config.VLM_COORD_SCALE) to frame pixels; clamp; drop tiny."""
    sc = config.VLM_COORD_SCALE
    out = []
    for o in objs if isinstance(objs, list) else []:
        b = o.get("bbox_2d") or o.get("bbox")
        if not b or len(b) < 4:
            continue
        try:
            x1 = int(float(b[0]) * w / sc); y1 = int(float(b[1]) * h / sc)
            x2 = int(float(b[2]) * w / sc); y2 = int(float(b[3]) * h / sc)
        except Exception:
            continue
        x1, x2 = sorted((max(0, min(x1, w)), max(0, min(x2, w))))
        y1, y2 = sorted((max(0, min(y1, h)), max(0, min(y2, h))))
        if x2 - x1 < 3 or y2 - y1 < 3:
            continue
        out.append({"label": str(o.get("label", "object")), "conf": 1.0, "box": (x1, y1, x2, y2)})
    return out[:config.VLM_MAX_OBJECTS]


SYSTEM_ANALYZE = (
    "You are a visual assistant looking at ONE image. Return STRICT JSON only, no markdown:\n"
    '{"answer": "<DIRECTLY answer the user request about THIS image. If they ask for a count, give the '
    'number. If yes/no, answer yes or no. Otherwise describe exactly what they asked about. Be specific, '
    '1-3 sentences.>", "objects": [{"label": "<short name>", "bbox_2d": [x1,y1,x2,y2]}]}\n'
    "For objects: box the item(s) the user asked about (e.g. every pillow, the person in the red hat); if "
    "the request is general, box the salient objects. Coordinates use a 0-1000 scale, (0,0)=top-left, "
    "(1000,1000)=bottom-right. If the asked item is absent, say so in answer and leave objects empty. "
    "Output valid JSON and nothing else."
)


def analyze(frame_bgr, prompt):
    """One reliable call -> (description, dets). The system prompt forces a JSON schema so boxes come
    EVERY time (no coaxing), with coords on a declared 0-1000 scale we map to frame pixels."""
    h, w = frame_bgr.shape[:2]
    user = prompt or "Describe the scene and highlight the notable objects."
    content = [{"type": "text", "text": user},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _b64(frame_bgr)}}]
    body = {"messages": [{"role": "system", "content": SYSTEM_ANALYZE},
                         {"role": "user", "content": content}],
            "temperature": 0.2, "max_tokens": 800}
    try:
        r = requests.post(config.LLAMA_URL + "/v1/chat/completions", json=body, timeout=config.VLM_TIMEOUT)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return (f"[VLM unavailable: {e}]", [])
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        data = json.loads(m.group(0) if m else txt)
    except Exception:
        return (txt, [])
    desc = str(data.get("answer") or data.get("description") or "").strip()
    return (desc or "(no description)", _scale_objects(data.get("objects", []), w, h))


def ground(frame_bgr, phrase):
    """Locate a DESCRIBED referent; [] when absent (VLM refuses instead of hallucinating). Boxes are
    scaled from the 0-1000 model space to frame pixels."""
    h, w = frame_bgr.shape[:2]
    prompt = (f'Detect {phrase} in the image. Output ONLY a JSON list like '
              f'[{{"bbox_2d":[x1,y1,x2,y2],"label":"..."}}] on a 0-1000 coordinate scale. '
              f'If it is not present, output [].')
    content = [{"type": "text", "text": prompt},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _b64(frame_bgr)}}]
    body = {"messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 300}
    try:
        r = requests.post(config.LLAMA_URL + "/v1/chat/completions", json=body, timeout=config.VLM_TIMEOUT)
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("ground error:", e); return []
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    return _scale_objects(arr, w, h)
