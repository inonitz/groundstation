"""llm_cv_scene main loop. A live camera window with four colour-coded overlay sources:
  grey    = always-on YOLOE background detections
  green   = YOLOE real-time highlight of what you asked for
  magenta = SAM2 mask of the same thing (the other selection method, to compare)
  amber   = the VLM's OWN one-shot grounding box (VLM grounding vs the detector)
Talk via your existing asr_node: press H there, speak; its transcript arrives on
/asr_server/transcribe, the brain answers on screen, and the eyes never stop -- no freeze.

Keys (in this window):  c clear highlight   t toggle SAM2   b toggle background   q quit
(H / push-to-talk is owned by the asr_node, not this window.)
"""
import time, textwrap
import cv2
import config, vlm
from eyes import Eyes
from ears import Ears


class State:
    answer = "press H at the asr_node to talk (e.g. 'what do you see?')"
    target = None
    vlm_box = None          # normalized (x1,y1,x2,y2)
    show_bg = True
    use_sam2 = True
    thinking = False


def draw_box(img, box, color, label=None, thick=2):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick)
    if label:
        cv2.putText(img, label, (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_panel(img, fps):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, h - 92), (w, h), (0, 0, 0), -1)
    y = h - 68
    for line in textwrap.wrap(State.answer, width=max(int(w / 9), 20))[:3]:
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    config.COL_TEXT, 1, cv2.LINE_AA)
        y += 22
    tag = "thinking..." if State.thinking else "ready (press H at asr_node)"
    hud = f"[{tag}] target={State.target or '-'}  sam2={'on' if State.use_sam2 else 'off'}  {fps:.0f} fps"
    cv2.putText(img, hud, (10, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                config.COL_HUD, 1, cv2.LINE_AA)


def main():
    eyes = Eyes(use_sam2=State.use_sam2)
    latest = {}

    def on_text(text):
        # runs on the rclpy spin thread (off the video loop): a transcript from asr_node
        State.thinking = True
        State.answer = "( " + text + " )"
        frame = latest.get("frame")
        if frame is None:
            State.thinking = False
            return
        ans, tgt, box = vlm.ask(frame, text, latest.get("dets", []))
        State.answer, State.target, State.vlm_box = ans, tgt, box
        eyes.set_target(tgt)
        State.thinking = False

    ears = Ears(on_text)
    cap = cv2.VideoCapture(config.CAM_INDEX)
    if not cap.isOpened():
        print("cannot open camera", config.CAM_INDEX); return
    cv2.namedWindow(config.WIN_NAME, cv2.WINDOW_NORMAL)

    t0, fps = time.time(), 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        latest["frame"] = frame.copy()

        dets = eyes.background(frame) if State.show_bg else []
        latest["dets"] = dets
        for d in dets:
            draw_box(frame, d["box"], config.COL_BACKGROUND, d["label"], 1)

        if State.target:
            hdets, mask = eyes.highlight(frame)
            if mask is not None and State.use_sam2:
                ov = frame.copy(); ov[mask] = config.COL_SAM2_HL
                cv2.addWeighted(ov, 0.45, frame, 0.55, 0, frame)
            for d in hdets:
                draw_box(frame, d["box"], config.COL_YOLOE_HL,
                         f'{State.target} {d["conf"]:.2f}', 2)

        if State.vlm_box:
            h, w = frame.shape[:2]
            bx = (int(State.vlm_box[0] * w), int(State.vlm_box[1] * h),
                  int(State.vlm_box[2] * w), int(State.vlm_box[3] * h))
            draw_box(frame, bx, config.COL_VLM_BOX, "VLM", 2)

        now = time.time(); fps = 0.9 * fps + 0.1 / max(now - t0, 1e-3); t0 = now
        draw_panel(frame, fps)
        cv2.imshow(config.WIN_NAME, frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('c'):
            State.target = None; State.vlm_box = None; eyes.set_target(None)
        elif k == ord('t'):
            State.use_sam2 = not State.use_sam2
        elif k == ord('b'):
            State.show_bg = not State.show_bg

    cap.release(); cv2.destroyAllWindows(); ears.shutdown()


if __name__ == "__main__":
    main()
