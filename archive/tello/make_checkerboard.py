#!/usr/bin/env python3
"""Emit the print-ready calibration board as a PDF at exact A4 scale.

PDF rather than SVG: an SVG's real-world size depends on the viewer that prints it, and a
browser will happily rescale it to fit its own margins, which silently breaks the whole
point of a scale-verified target. A PDF page carries its size in the file.

The board must be backed by something flat and rigid, and the backing needs to be at least
as big as the board itself. Pass a smaller square size if yours is small: a 13 mm board is
130x91 mm and fits the front cover of an A5 notebook.

Usage: python3 make_checkerboard.py [square_size_mm]   (default 20)
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MM_PER_INCH = 25.4
PAGE_W, PAGE_H = 297.0, 210.0          # A4 landscape
SAFE = 12.0                            # consumer printers cannot print nearer the edge
COLS, ROWS = 10, 7
BAR_LEN = 100.0


def main():
	SQ = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
	BOARD_W, BOARD_H = COLS * SQ, ROWS * SQ
	assert BOARD_W <= PAGE_W - 2 * SAFE and BOARD_H <= PAGE_H - 2 * SAFE - 40.0, \
		f"{SQ:.0f}mm squares make a {BOARD_W:.0f}x{BOARD_H:.0f}mm board, too big for A4"

	# Top-down mm, converted on use. Designing against the page top reads more naturally
	# than PDF's y-up origin.
	board_x = (PAGE_W - BOARD_W) / 2.0
	# Keep the board vertically centred in the space above the ruler strip, whatever its size.
	board_top = 30.0 + (PAGE_H - 40.0 - 30.0 - BOARD_H) / 2.0
	title_top, bar_top, caption_top = 24.0, 182.0, 190.0
	flip = lambda y: PAGE_H - y

	fig = plt.figure(figsize=(PAGE_W / MM_PER_INCH, PAGE_H / MM_PER_INCH))
	ax = fig.add_axes([0, 0, 1, 1])
	ax.set_xlim(0, PAGE_W)
	ax.set_ylim(0, PAGE_H)
	ax.set_aspect("equal")
	ax.axis("off")

	for r in range(ROWS):
		for c in range(COLS):
			if (r + c) % 2 == 0:
				ax.add_patch(Rectangle((board_x + c * SQ, flip(board_top + (r + 1) * SQ)),
				                       SQ, SQ, facecolor="black", edgecolor="none"))

	ax.text(board_x, flip(title_top),
	        f"{COLS}x{ROWS} squares = {COLS-1}x{ROWS-1} inner corners, {SQ:.0f} mm nominal. "
	        "Print A4 landscape at 100%, fit-to-page OFF.", fontsize=9, va="baseline")

	# Two independent scale checks. The board spans a known width, so even a clipped bar
	# leaves a way to verify the print.
	bar_y = flip(bar_top)
	ax.plot([board_x, board_x + BAR_LEN], [bar_y, bar_y], color="black", lw=2.5,
	        solid_capstyle="butt")
	for i in range(11):
		x = board_x + i * (BAR_LEN / 10.0)
		tick = 3.5 if i % 5 == 0 else 2.0
		ax.plot([x, x], [bar_y - tick, bar_y + tick], color="black", lw=1.2)

	ax.text(board_x, flip(caption_top),
	        f"Scale check: this bar is {BAR_LEN:.0f} mm, and the board is {BOARD_W:.0f} mm "
	        f"across all {COLS} squares. Either one must measure true.",
	        fontsize=8, va="baseline")

	for name, x0, y0, x1, y1 in (
		("board", board_x, board_top, board_x + BOARD_W, board_top + BOARD_H),
		("bar", board_x, bar_top - 3.5, board_x + BAR_LEN, bar_top + 3.5),
	):
		assert x0 >= SAFE and y0 >= SAFE and x1 <= PAGE_W - SAFE and y1 <= PAGE_H - SAFE, \
			f"{name} falls outside the {SAFE}mm safe area"

	out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
	                   f"checkerboard_a4_{COLS-1}x{ROWS-1}_{SQ:.0f}mm.pdf")
	fig.savefig(out)   # no bbox_inches="tight" -- that would crop the page and rescale it
	plt.close(fig)
	print(f"wrote {out}: A4 landscape, board {BOARD_W:.0f}x{BOARD_H:.0f} mm, "
	      f"{COLS-1}x{ROWS-1} inner corners")
	return


if __name__ == "__main__":
	main()
