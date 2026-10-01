"""See the labelling page in a real (headless) browser: every card state, desktop and
phone width, on a COPY of the recordings file. Needs install-browser.sh.

    PYTHONPATH=/root/.venvs/asr-verify-browser python3 \\
        /root/groundstation/tools/asr-verify-transcript/screenshots.py [out_dir]
Prints every browser console error ("BROWSER ERROR: ...")."""
import os
import shutil
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import labels                                     # noqa: E402
import server                                     # noqa: E402

SIZES = {"desktop": (1400, 1000), "phone": (390, 844)}


def start(copy_dir):
    """A server on a copy of the owner's file, on a free port. -> (server, url)."""
    out = os.path.join(copy_dir, "recordings.json")
    if os.path.exists(labels.OUT):
        shutil.copy(labels.OUT, out)
    srv = server.serve(labels.Recordings(out), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def states(page, url, shoot):
    """Walk the card through every state, one screenshot each."""
    page.goto(url + "#1")
    page.wait_for_selector("#options .option")
    shoot("clip")
    page.click("#k-mission")
    page.wait_for_timeout(300)
    for action in labels.ROW_ACTIONS:
        page.click("#add-step")
        page.locator("#rows .row select").last.select_option(action)
        if action not in ("take off", "land"):
            page.locator("#rows .row input").last.fill("3")
    page.wait_for_timeout(400)
    shoot("every-step")
    page.click("#k-none")
    shoot("nothing-flies")
    page.click("#k-emergency")
    shoot("halt")
    page.click("#k-perception")
    page.wait_for_timeout(400)
    shoot("vision")
    page.locator("#options .option").nth(1).locator("[data-use=both]").click()
    page.wait_for_timeout(400)
    shoot("recommendation-used")
    page.click("#remove")
    shoot("remove-form")
    page.goto(url + "#70")
    page.wait_for_timeout(600)
    shoot("whisper-wrote-nothing")
    page.fill("#sentence", "עלה עשרה מטרים")
    page.wait_for_timeout(800)
    shoot("typed-sentence-nearest")
    return


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="asr-ui-")
    errors = []
    copy_dir = tempfile.mkdtemp(prefix="asr-copy-")
    srv, url = start(copy_dir)
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for size, (width, height) in SIZES.items():
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: errors.append(msg.text) if msg.type == "error" else None
            )

            def shoot(name, page=page, size=size):
                page.screenshot(
                    path=os.path.join(out_dir, f"{size}-{name}.png"),
                    full_page=True
                )
                return

            states(page, url, shoot)
            page.close()
        browser.close()
    srv.shutdown()

    print(f"screenshots: {out_dir}")
    for error in errors:
        print("BROWSER ERROR:", error)
    print(f"{len(errors)} browser errors")
    return


if __name__ == "__main__":
    main()
