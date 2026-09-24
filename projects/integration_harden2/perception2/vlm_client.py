"""Gemma vision questions: frame + detector hints + the user's question -> a spoken-style
answer, and, for a find/highlight request, a target phrase plus Gemma's own box guess.

The prompt and the reply parsing are perception's own. Talking to Gemma goes through the
ONE shared client (gemma/client.py); keeping Gemma alive is the gemma package's job, not
this file's. parse_reply() is pure text, so it is testable offline.
"""
import base64
import re

import cv2

import config


SYSTEM = (
    "You are a computer-vision system looking through a live camera. Answer the user's "
    "question DIRECTLY about what is actually in THIS image -- objects, people, "
    "clothing, colours, text, count, and where things are. Vary your wording; never "
    "repeat a canned description. If something asked about is not visible, say so "
    "plainly. Answer in the SAME LANGUAGE as the user's question (a Hebrew question "
    "gets a Hebrew answer; the HIGHLIGHT line is ALWAYS English). No emoji.\n"
    "\n"
    "ALWAYS format your reply as EXACTLY these two labelled sections, in this order:\n"
    "LONG RESPONSE: <1-3 sentences, detailed -- this is shown on screen>\n"
    "SHORT RESPONSE: <ONE brief natural sentence -- this is spoken aloud, so be "
    "concise; no lists, no rambling>\n"
    "For counting questions (how many / count), BEGIN both responses with the exact "
    "integer, e.g. '2 people.'\n"
    "\n"
    "A fast detector also lists objects it found (labels + boxes) as a hint -- use it, "
    "but trust your own eyes.\n"
    "ONLY if the user asks to find/point at/highlight a specific thing, add two MORE "
    "final lines after the responses:\n"
    "HIGHLIGHT: <a concrete noun phrase a detector can localize, e.g. 'the person in "
    "the black hat' or 'red backpack'; or none>\n"
    "VLM_BOX: x1,y1,x2,y2   (normalized 0-1, top-left origin; omit if unsure)"
)


def _b64(frame_bgr):
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return ""
    return base64.b64encode(buf).decode()


def _dets_text(dets):
    if not dets:
        return "(detector found nothing this frame)"
    return "\n".join(f'- {d["label"]} at {list(d["box"])}' for d in dets[:20])


VLM_GRAMMAR = (
    r"""
root ::= "LONG RESPONSE: " line "\nSHORT RESPONSE: " line"""
    r""" ("\nHIGHLIGHT: " hl "\nVLM_BOX: " box)?
line ::= [^\n]+
hl ::= "none" | [^\n]+
box ::= "none" | num "," num "," num "," num
num ::= [0-9]+ ("." [0-9]+)?
"""
)


def ask(gemma, frame_bgr, question, dets):
    """Ask Gemma (a gemma.client.Gemma) about the frame. -> (status, reply). status is
    True on success. reply = (long_text, highlight_target|None, vlm_box|None, short_text)
    when status is True, else None. vlm_box is normalized xyxy."""
    content = [
        {
            "type": "text",
            "text": f"Detector found:\n{_dets_text(dets)}\n\nUser asks: {question}",
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + _b64(frame_bgr)},
        },
    ]
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": content},
    ]
    ok, text = gemma.request(
        messages,
        grammar=VLM_GRAMMAR,
        max_tokens=256,
        timeout_s=config.VLM_TIMEOUT
    )
    if not ok:
        return False, None
    return True, parse_reply(text)


def parse_reply(txt):
    """Split the model's labelled reply into (long, target, box, short). Pure text;
    testable."""
    target = None
    box = None

    # the highlight target and Gemma's own box, when the reply has them
    m = re.search(r"HIGHLIGHT:\s*(.+)", txt)
    if m:
        t = m.group(1).strip().strip(".")
        if t.lower() not in ("none", "n/a", ""):
            target = t
    m = re.search(
        r"VLM_BOX:\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)",
        txt
    )
    if m:
        box = tuple(float(x) for x in m.groups())

    # the two responses, never with their labels
    body = re.split(r"\n?HIGHLIGHT:", txt)[0]
    lm = re.search(
        r"LONG RESPONSE:\s*(.+?)(?=\n*\s*SHORT RESPONSE:|\Z)",
        body,
        re.S | re.I
    )
    sm = re.search(r"SHORT RESPONSE:\s*(.+)", body, re.S | re.I)
    long_txt = (lm.group(1) if lm else body).strip()
    short_txt = (sm.group(1) if sm else "").strip()
    # never leak labels
    long_txt = re.sub(r"\b(LONG|SHORT) RESPONSE:\s*", "", long_txt, flags=re.I).strip()
    # model gave no short -> first sentence of long
    if not short_txt and long_txt:
        short_txt = re.split(r"(?<=[.!?])\s+", long_txt)[0].strip()
    long_txt = long_txt or "(no answer)"
    short_txt = re.sub(r"\b(LONG|SHORT) RESPONSE:\s*", "", short_txt, flags=re.I)
    short_txt = short_txt.strip() or long_txt
    # (screen_long, highlight_target, box, spoken_short)
    return (long_txt, target, box, short_txt)
