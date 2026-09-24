"""Box geometry for perception2: ONE home for the overlap math. A box is
(x1, y1, x2, y2) in pixels, top-left origin."""


def frame_area(frame):
    """A frame's area in pixels."""
    return frame.shape[0] * frame.shape[1]


def area(b):
    """The box area; 0 for an inverted box."""
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def intersection(a, b):
    """The area two boxes share; 0 when they do not overlap."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def iou(a, b):
    """Intersection over union; 0.0 when the boxes do not overlap."""
    inter = intersection(a, b)
    if inter <= 0:
        return 0.0
    return inter / (area(a) + area(b) - inter)


def inside(a, b):
    """The fraction of box a that lies inside box b."""
    return intersection(a, b) / max(1, area(a))
