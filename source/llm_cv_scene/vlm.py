"""llama-server client for the reasoning brain (Qwen3-VL-4B). Sends the current frame +
the detector's findings + the operator's question. Returns a spoken-style answer and,
when the operator asked to find something, a target phrase plus the VLM's own box guess
(so you can compare VLM grounding against the real-time detector on screen). Never raises."""
import base64, re, cv2, requests
import config

SYSTEM = (
    "You are the perception brain of a drone. You see ONE camera frame and a list of "
    "objects a real-time detector already found (labels + pixel boxes). Answer the "
    "operator's question about the scene in 1-3 natural sentences: what you see, where, "
    "and a notable detail. Be concrete and HONEST -- if something asked about is not "
    "visible, say so plainly; never invent it.\n"
    "If the operator asks to find/highlight/point at a specific thing, add as the LAST "
    "lines, exactly:\n"
    "HIGHLIGHT: <short search label, or none>\n"
    "VLM_BOX: x1,y1,x2,y2   (normalized 0-1, top-left origin; omit the line if unsure)"
)

def _b64(frame_bgr):
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode() if ok else ""

def _dets_text(dets):
    if not dets:
        return "(detector found nothing this frame)"
    return "\n".join(
        f'- {d["label"]} at {list(d["box"])}' for d in dets[:20]
    )

def ask(frame_bgr, question, dets):
    """-> (answer_text, highlight_target|None, vlm_box|None). vlm_box is normalized xyxy."""
    content = [
        {"type": "text",
         "text": f"Detector found:\n{_dets_text(dets)}\n\nOperator asks: {question}"},
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + _b64(frame_bgr)}},
    ]
    body = {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": content}],
            "temperature": 0.2, "max_tokens": 256}
    try:
        r = requests.post(config.LLAMA_URL + "/v1/chat/completions",
                          json=body, timeout=config.VLM_TIMEOUT)
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
