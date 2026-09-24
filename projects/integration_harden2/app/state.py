"""The app's shared state: one lock and the values the screen, the vision tasks and the
turn handler all read. Every read and write of these fields holds S.lock."""
import collections
import threading


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.hl_dets = []
        self.hl_masks = []
        self.target = None
        self.thinking = False
        self.use_sam = True
        self.chat = collections.deque(maxlen=60)
        self.chat_scroll = 0       # chat rows scrolled up from the newest (0 = follow)
        return


S = Shared()

