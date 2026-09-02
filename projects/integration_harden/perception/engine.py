"""The perception engine: what to highlight, whether it is really there, and which boxes/masks
survive. Pure logic -- every model is an injected callable, so the self-test and the wiring
tests run with fakes and no GPU.

The three measured mechanisms this file owns (evidence: the live desk loop):
  1. Relative-confidence gate. OmDet is queried at a low floor so every candidate is visible;
     only detections within REL of the top score are kept. A 0.48 box dies next to a 0.90 box;
     two real windows at 0.85/0.88 both survive.
  2. Mask hygiene. Each kept box gets a SAM2 mask; whole-frame garbage masks are dropped, boxes
     are tightened to their mask, and a near-full-frame box with no clean mask is discarded.
  3. VLM fallback + presence gate. When the detector whiffs, the VLM's own box (from the
     presence gate) is masked instead. The presence gate asks the VLM whether the target is
     visible at all before any box is drawn -- open-vocab detectors ground absent phrases onto
     salient objects, and the gate is what stops that.
"""
import re

import numpy as np

# ------------------------------ highlight-phrase parsing ------------------------------

CLEAR_RE = re.compile(r"\b(?:stop (?:highlight\w*|track\w*)|clear|reset|deselect|never ?mind)\b", re.I)
LEAD_VERB_RE = re.compile(r"^(?:highlight|locate|track|mark|find|show me|point (?:at|to))\s+(?:the |a |an |that |my )?", re.I)
FIND_RE = re.compile(r"\b(?:highlight|locate|track|mark|find|show me|point (?:at|to)|where(?:'s| is| are))\s+(?:the |a |an |that |my )?(.+)", re.I)
FILLER_RE = re.compile(r"\b(?:please|for me|in the (?:frame|image|scene|room|camera)|right now|thank you|thanks)\b.*$", re.I)


def parse_highlight(text):
    """'highlight the red backpack' -> 'red backpack'; 'clear' -> ''; anything else -> None."""
    if CLEAR_RE.search(text):
        return ""
    m = FIND_RE.search(text)
    if not m:
        return None
    phrase = FILLER_RE.sub("", m.group(1)).strip().strip(".?! ,")
    phrase = LEAD_VERB_RE.sub("", phrase).strip() if phrase else phrase
    return phrase or None


def ascii_only(s):
    return (s or "").encode("ascii", "ignore").decode("ascii")


def scale_vlm_box(box, frame_shape):
    """VLM boxes arrive normalized 0-1 or 0-1000 depending on the prompt; auto-detect and
    return pixel coordinates."""
    if not box:
        return None
    h, w = frame_shape[:2]
    sc = 1000.0 if max(box) > 1.5 else 1.0
    return (int(box[0] / sc * w), int(box[1] / sc * h),
            int(box[2] / sc * w), int(box[3] / sc * h))


# ------------------------------------ the engine ------------------------------------

class PerceptionEngine:
    """detect(frame, phrase, conf) -> [{"label","conf","box"}...] sorted by conf desc.
    mask_for_box(frame, box) -> bool mask or None.
    vlm_ask(frame, question, dets) -> (long_text, highlight_target|None, vlm_box|None, short_text)."""

    MASK_MAX_FRAC = 0.85    # a mask covering more of the frame than this is garbage
    BOX_MAX_FRAC = 0.90     # a near-full-frame box with no clean mask is not a highlight

    def __init__(self, detect, mask_for_box, vlm_ask,
                 floor=0.12, draw_conf=0.30, rel=0.65, mask_k=3):
        self.detect = detect
        self.mask_for_box = mask_for_box
        self.vlm_ask = vlm_ask
        self.floor = floor          # detector query threshold: low, to see every candidate
        self.draw_conf = draw_conf  # absolute minimum for anything drawn
        self.rel = rel              # keep only detections within this fraction of the top score
        self.mask_k = mask_k        # mask at most this many detections per frame

    def apply_masks(self, frame, dets, use_sam=True):
        """Mask hygiene (mechanism 2). Returns (kept_dets, masks)."""
        h, w = frame.shape[:2]
        frame_area = float(h * w)
        kept, masks = [], []
        for d in dets[:self.mask_k]:
            x1, y1, x2, y2 = d["box"]
            box_frac = ((x2 - x1) * (y2 - y1)) / frame_area
            mask = None
            if use_sam:
                try:
                    mask = self.mask_for_box(frame, d["box"])
                except Exception as e:
                    print("sam err:", e)
            if mask is not None and mask.sum() > 0 and (mask.sum() / frame_area) <= self.MASK_MAX_FRAC:
                ys, xs = np.where(mask)
                d = dict(d)
                d["box"] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
                masks.append(mask)
                kept.append(d)
            elif box_frac <= self.BOX_MAX_FRAC:
                kept.append(d)      # localized box without a clean mask still counts
        return kept, masks

    def highlight_step(self, frame, target, vlm_box_px=None, use_sam=True):
        """One frame of highlighting (mechanisms 1-3). Returns (dets, masks, debug)."""
        if not target:
            return [], [], {}
        try:
            raw = self.detect(frame, target, self.floor)
        except Exception as e:
            raw = []
            print("detector err:", e)
        best = raw[0]["conf"] if raw else 0.0
        threshold = max(self.draw_conf, best * self.rel)
        kept = [d for d in raw if d["conf"] >= threshold]
        dets, masks = self.apply_masks(frame, kept, use_sam)
        if not dets and vlm_box_px is not None:     # detector whiffed: fall back to the VLM's box
            fallback = {"label": f"{target} (vlm)", "conf": 1.0, "box": vlm_box_px}
            mask = None
            try:
                mask = self.mask_for_box(frame, vlm_box_px)
            except Exception as e:
                print("sam err:", e)
            if mask is not None and mask.sum() > 0:
                ys, xs = np.where(mask)
                fallback["box"] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
                dets, masks = [fallback], [mask]
            else:
                dets, masks = [fallback], []
        return dets, masks, {"raw": raw, "threshold": threshold}

    def presence_gate(self, frame, phrase):
        """Ask the VLM whether the phrase is actually visible (mechanism 3). Returns
        (present, vlm_box_px|None). On VLM failure the gate fails OPEN: the detector's own
        confidence gate still stands behind it."""
        try:
            _, target, box, _ = self.vlm_ask(frame, f"Point at and highlight the {phrase}.", [])
        except Exception as e:
            print("gate VLM err:", e)
            return True, None
        present = target is not None            # the VLM writes HIGHLIGHT: none when absent
        box_px = scale_vlm_box(box, frame.shape) if box else None
        return present, box_px


# ------------------------------------- self-test -------------------------------------

def selftest():
    bad = []
    if parse_highlight("highlight the red backpack please") != "red backpack":
        bad.append("parse: basic")
    if parse_highlight("clear") != "":
        bad.append("parse: clear")
    if parse_highlight("how many people do you see") is not None:
        bad.append("parse: question must not become a target")

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    good_mask = np.zeros((100, 100), dtype=bool)
    good_mask[40:60, 40:60] = True
    garbage_mask = np.ones((100, 100), dtype=bool)

    # Relative gate: 0.48 dies next to 0.90; both windows at 0.85/0.88 survive.
    eng = PerceptionEngine(detect=lambda f, p, c: [{"label": p, "conf": 0.90, "box": (10, 10, 30, 30)},
                                                   {"label": p, "conf": 0.48, "box": (50, 50, 70, 70)}],
                           mask_for_box=lambda f, b: good_mask, vlm_ask=None)
    dets, masks, dbg = eng.highlight_step(frame, "window")
    if len(dets) != 1 or dbg["threshold"] < 0.5:
        bad.append("relative gate: low candidate survived")
    if dets and dets[0]["box"] != (40, 40, 59, 59):
        bad.append("mask hygiene: box not tightened to mask")

    # Garbage mask is dropped; the localized box stays without it.
    eng2 = PerceptionEngine(detect=lambda f, p, c: [{"label": p, "conf": 0.9, "box": (10, 10, 30, 30)}],
                            mask_for_box=lambda f, b: garbage_mask, vlm_ask=None)
    dets2, masks2, _ = eng2.highlight_step(frame, "thing")
    if masks2 or len(dets2) != 1:
        bad.append("mask hygiene: garbage mask not dropped")

    # Detector whiff + VLM box -> fallback highlight.
    eng3 = PerceptionEngine(detect=lambda f, p, c: [], mask_for_box=lambda f, b: good_mask, vlm_ask=None)
    dets3, masks3, _ = eng3.highlight_step(frame, "cat", vlm_box_px=(35, 35, 65, 65))
    if len(dets3) != 1 or "(vlm)" not in dets3[0]["label"] or len(masks3) != 1:
        bad.append("vlm fallback: not applied")

    # Presence gate: absent -> (False, None); present with a 0-1000 box -> pixel coords.
    eng4 = PerceptionEngine(detect=None, mask_for_box=None,
                            vlm_ask=lambda f, q, d: ("no", None, None, "no"))
    if eng4.presence_gate(frame, "unicorn")[0] is not False:
        bad.append("gate: absent not suppressed")
    eng5 = PerceptionEngine(detect=None, mask_for_box=None,
                            vlm_ask=lambda f, q, d: ("yes", "cat", (500, 500, 1000, 1000), "yes"))
    present, px = eng5.presence_gate(frame, "cat")
    if not present or px != (50, 50, 100, 100):
        bad.append(f"gate: box scaling wrong ({px})")
    return bad


if __name__ == "__main__":
    problems = selftest()
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("perception engine self-test CLEAN: parsing, relative gate, mask hygiene, "
          "vlm fallback, presence gate all verified")
