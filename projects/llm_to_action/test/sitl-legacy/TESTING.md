# SITL follow / hover test guide

How to test the FOLLOW + HOVER + grammar work end to end. Two ways: capture logs for
review, or watch it live with your own eyes. Both are one command to start.

Prereq: px4 is already built (`./build.sh release shared px4 build`). Nothing else to set up.

There are two scenarios:
- **follow/** — one moving person. Tests hold, re-acquire, hover, no re-takeoff, clean grammar.
- **crowd/** — three people (one red, centre). Tests the stable-id tracker (three ids, no swap)
  and "follow the middle person".

---

## Test 1 — capture logs for review

Do NOT use `script`. The sim runs in tmux, and `script` records the screen with cursor
codes -- garbage. The FMU already tees its own clean stdout to `captured_panes_log.txt`
in the scenario folder (see `sim_core.sh`). That file IS the log. Just run the scenario:

Every run writes a UNIQUE timestamped log to `projects/llm_to_action/test/sitl-legacy/runs/`, so runs never
overwrite and we can correlate what you saw with the exact file.

Start a run (one moving person, or the 3-person crowd):
```bash
cd /root/groundstation/projects/llm_to_action/test/sitl-legacy
./logtest.sh follow       # or:  ./logtest.sh crowd
```
It prints the log path, e.g. `runs/follow_20260812T143005.log`. Let it run ~2 min, then
**Ctrl-B then D** to detach cleanly (or **Ctrl-C** to stop).

Get the digest of the newest run:
```bash
cd /root/groundstation/projects/llm_to_action/test/sitl-legacy
./digest.sh
```
It prints the numbers, saves `runs/<scenario>_<stamp>.digest.txt`, and tells you exactly
which file to send me. Send that `.digest.txt` (and the `.log` if you want a deep read).

**What good looks like:** takeoffs 1, takeoff_rejected 0, parameters 0, FOLLOW activated >=1,
HOVER activated 0 (this objective is a follow, not a bare hold), many follow servo ticks,
no crashes. HOVER activated > 0 here means the model wrongly chose hover over follow.

---

## Test 2 — watch with your own eyes

Start a scenario (same as above, or just `./watch.sh` without `script`). In a second
terminal with the ROS workspace sourced:
```bash
cd /root/groundstation
python3 scripts/dashboard/serve.py 8088     # open http://localhost:8088
```

The dashboard shows three things: the annotated camera (boxes drawn `#<track_id> person NN%`),
the executed-command list with status, and the VLM's thoughts per cycle.

Watch for this, per scenario.

**follow/ (single person):**
- After takeoff it issues `follow` once, then the command list goes quiet. It does NOT keep
  issuing `go` / `takeoff` / `search`.
- The drone turns in place to keep the person centred. It does NOT fly toward them.
- When the person walks out of frame briefly, the drone holds still and re-locks when they
  come back. No flailing.

**crowd/ (three people):**
- Each of the three boxes keeps the SAME `#id` as they move. Ids do not swap when two pass near.
- It follows the centre (red) person and holds that id.

**Bad signs to report:** the drone drifts/translates during follow; the command list keeps
stacking `go` or re-`takeoff`; an id jumps to a new number every second; it "looks around"
searching for a person that is clearly on screen.

If you see a bad sign, note which one + roughly when, and grab `full_run.log` (Test 1). That
pins it to the exact log lines.

---

## Stop cleanly

Press **Ctrl-C** in the scenario terminal first (finalises the `script` log), then close the
tmux session. Killing the session first is fine too — `script -f` flushes continuously, so you
keep everything already written.
