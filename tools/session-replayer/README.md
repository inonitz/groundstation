# MVD session replayer

Open `replayer.html` in a browser, click "Open a session folder", and pick a
`projects/integration_harden2/sessions/session-*` folder. Everything is read in the
browser (File API) — nothing is uploaded; the private session data never leaves the machine.

It reads the session's `trace.jsonl` (one line per utterance) and, for perception utterances,
the `perception/<seq>-<kind>-<target>/` dir: `request.json` + each `pass_NNNNN.{jpg,json}`.
Raw frames are stored model-agnostically (no burned-in boxes); the replayer draws the boxes from
the JSON, so the same frames can later be re-scored by a different model. "export annotated" burns
the current pass to a jpg on demand.
