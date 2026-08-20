#!/usr/bin/env python3
"""Real-time multi-object TRACKING prototype (BoT-SORT: camera-motion compensation + Re-ID).
SEPARATE from the frozen VLM demo in ../llm_cv_scene -- reuses its downloaded weights, touches nothing.

  python3 track.py --classes person     # closed-set YOLO26, track people (fast/reliable)
  python3 track.py --open "person"       # open-vocab YOLOE-26x (any phrase)
  python3 track.py --source 0            # webcam instead of the drone feed
Window: press q or Esc to quit.
"""
import os, argparse, cv2
SCENE = "/root/groundstation/source/llm_cv_scene"   # reuse weights already downloaded there

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("SCENE_INPUT", "rtsp://127.0.0.1:8554/live"))
    ap.add_argument("--open", default=None, help="open-vocab phrase -> YOLOE-26x")
    ap.add_argument("--classes", default=None, help="comma COCO class names -> YOLO26")
    ap.add_argument("--model", default=None)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.3)
    a = ap.parse_args()
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    classes = None
    if a.open:
        from ultralytics import YOLOE
        model = YOLOE(a.model or f"{SCENE}/yoloe-26x-seg.pt")
        try: model.set_classes([a.open], model.get_text_pe([a.open]))
        except Exception: model.set_classes([a.open])
        print(f"[track] open-vocab YOLOE-26x: {a.open!r}")
    else:
        from ultralytics import YOLO
        model = YOLO(a.model or f"{SCENE}/yolo26n-seg.pt")
        if a.classes:
            names = {v: k for k, v in model.names.items()}
            classes = [names[c.strip()] for c in a.classes.split(",") if c.strip() in names]
        print(f"[track] YOLO26: {a.classes or 'all COCO classes'}")

    win = "llm_cv_track"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print(f"[track] source={a.source}  tracker=BoT-SORT (CMC+ReID)  -- press q or Esc to quit")
    # stream=True yields per-frame results so WE own the loop (and the quit key). result.plot()
    # renders boxes + persistent track IDs.
    for result in model.track(source=a.source, tracker="botsort.yaml", persist=True, stream=True,
                              conf=a.conf, imgsz=a.imgsz, classes=classes, verbose=False):
        cv2.imshow(win, result.plot())
        k = cv2.waitKey(1) & 0xFF
        if k in (27, ord('q')):
            break
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
