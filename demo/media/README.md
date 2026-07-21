# Demo video pipeline

Three steps, run in order from the repo root:

1. **`vhs demo/walkthrough.tape`** -- renders the CLI half
   (`demo-walkthrough.mp4`) by typing `demo/README.md`'s Walkthrough
   commands against `mock-shell.sh`'s replay of real captured output
   (`fixtures/`). Deterministic, no live stack needed. See the tape's
   own header comment and `fixtures/README.md`.

2. **`python3 demo/media/capture_dashboard.py`** -- renders the
   dashboard half. Unlike the CLI half, this one's real: it needs
   `keycloak` + `combiner` + the six candidate trustees already up and
   registered (see its docstring for the exact precondition), then it
   drives one real live ceremony through pause/curl/docker commands
   while a headless Chrome tab sits on `/dashboard`, video-recording the
   whole thing via Playwright. Writes
   `dashboard-recording/page@*.webm` plus `dashboard-timeline.json` (the
   wall-clock offset of each named beat -- erin_paused, ceremony_formed,
   vault_created, dave_frank_paused, verified, etc.).

3. **`demo/media/compose_full_video.sh`** -- concatenates the two into
   `demo-walkthrough-full.mp4`: the CLI walkthrough, a title card, then
   the dashboard capture in full. A straight two-act composition, not a
   frame-by-frame interleave -- see the script's own header comment for
   why, and for what a finer interleave would need
   (`dashboard-timeline.json`'s real offsets, matched against the CLI
   tape's own `# SPLICE:` comments).

Playwright needs its own bundled ffmpeg for video recording, separate
from system ffmpeg: `python3 -m playwright install ffmpeg` (one-time).
`capture_dashboard.py` launches via `channel="chrome"`, reusing whatever
`google-chrome` is already installed rather than downloading a separate
Chromium -- if that's not on the machine, either install it or switch
the launch call to Playwright's own bundled Chromium
(`playwright install chromium --with-deps`, needs sudo for system
deps).

Generated outputs (`*.mp4`, `*.gif`, `dashboard-recording/`,
`dashboard-timeline.json`) are gitignored -- rerun the pipeline rather
than expecting them to already be on disk after a fresh checkout.
