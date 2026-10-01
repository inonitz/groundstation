"""The page in a REAL headless browser (owner B4 (8)): the nearest cases work, the remove
buttons line up, a clip can be removed with a reason. Needs install-browser.sh; skipped
without it:
    PYTHONPATH=/root/.venvs/asr-verify-browser python3 -m pytest -q test_page.py"""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels as L
import server


@pytest.fixture
def page(tmp_path):
    # skipped when the browser is not installed (install-browser.sh)
    sync_api = pytest.importorskip("playwright.sync_api")
    srv = server.serve(L.Recordings(str(tmp_path / "recordings.json")), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors = []
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        tab = browser.new_page(viewport={"width": 1400, "height": 1000})
        tab.on("pageerror", lambda exc: errors.append(str(exc)))
        tab.base = f"http://127.0.0.1:{srv.server_address[1]}/"
        tab.out = tmp_path / "recordings.json"
        yield tab
        browser.close()
    srv.shutdown()
    assert errors == []


def test_the_nearest_cases_fill_the_sentence_and_the_plan(page):
    page.goto(page.base + "#20")
    page.wait_for_selector("#options .option")
    assert page.locator("#options .option").count() == L.ALTERNATIVES
    second = page.locator("#options .option").nth(1)
    offered = second.locator(".he").inner_text()
    second.locator("[data-use=both]").click()
    page.wait_for_timeout(300)
    assert page.input_value("#sentence") == offered
    assert page.inner_text("#sentence-tag") == "edited"
    assert page.inner_text("#plan") == second.locator(".words").inner_text()


def test_the_nearest_cases_follow_a_typed_sentence_when_whisper_wrote_nothing(page):
    page.goto(page.base + "#70")                        # clips 63-100: no whisper text
    page.wait_for_timeout(500)
    assert page.locator("#options .option").count() == 0
    page.fill("#sentence", "עלה עשרה מטרים")
    page.wait_for_selector("#options .option")
    assert page.locator("#options .option .he").first.inner_text() == "עלה עשרה מטרים"


def test_every_remove_button_lines_up(page):
    page.goto(page.base + "#20")
    page.wait_for_selector("#options .option")
    page.click("#k-mission")
    for action in L.ROW_ACTIONS:
        page.click("#add-step")
        page.locator("#rows .row select").last.select_option(action)
    page.wait_for_timeout(300)
    xs = {
        round(page.locator("#rows .row .remove").nth(i).bounding_box()["x"])
        for i in range(page.locator("#rows .row").count())
    }
    assert len(xs) == 1                           # one column, take off and land too


def test_a_clip_is_removed_with_its_reason(page):
    page.goto(page.base + "#92")
    page.wait_for_selector("#remove")
    page.click("#remove")
    page.fill("#remove-why", "too much of the same sentence")
    page.press("#remove-why", "Enter")
    page.wait_for_timeout(500)
    cases = json.load(open(page.out, encoding="utf-8"))["cases"]
    assert len(cases) == 1 and cases[0]["removed"] is True
    assert cases[0]["removed_reason"] == "too much of the same sentence"
    assert cases[0]["expect"] == {"kind": "review"}
    page.goto(page.base + "#92")
    page.reload()                                   # a hash change alone does not load
    page.wait_for_timeout(500)
    assert page.inner_text("#badge") == "Removed: too much of the same sentence"


def test_hidden_parts_stay_hidden(page):
    """A display rule must not show a hidden part: the removal form until asked, the
    step rows outside a flight plan."""
    page.goto(page.base + "#20")
    page.wait_for_selector("#options .option")
    assert not page.is_visible("#remove-form")
    page.click("#k-none")
    assert not page.is_visible("#rows") and not page.is_visible("#add-step")
    page.click("#remove")
    assert page.is_visible("#remove-form")
