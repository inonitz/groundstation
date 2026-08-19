"""llama-server client for the reasoning brain (Qwen3-VL-4B). Sends the current frame + the
detector's findings + the user's question. Returns a spoken-style answer and, when the user asked
to find something, a target phrase plus the VLM's own box guess. Never raises."""
import base64, re, cv2, requests
import config

SYSTEM = (
    "You are a visual assistant looking through a live camera. Answer the user's question "
    "DIRECTLY and specifically about what is actually in THIS image -- the objects, people, "
    "clothing, colours, text, count, and where things are. Vary your wording each time; never "
    "repeat a canned description. 1-3 sentences unless asked for more. If something asked about "
    "is not visible, say so plainly.\n"
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
