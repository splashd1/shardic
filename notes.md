# Session notes — 2026-07-11 (later)

## What happened

Two things, continuing from the CI-activation work earlier today:

1. **Verified the CI/release pipeline actually works end-to-end.**
   Checked `gh run list` / `gh release list` and found both the
   `main`-push build and the `v1.0.0` tag-triggered release had
   already run successfully — all 8 assets (both `.exe`s, both Linux
   binaries, both AppImages) are attached to the `v1.0.0` GitHub
   Release. This closes out the "verify first live CI run" follow-up
   from the earlier entry below — it's done, not just activated.
2. **Built cross-machine session sync** (commit `fd85baf`):
   - `.claude/hooks/session-start-sync.sh` + a `SessionStart` hook in
     `.claude/settings.json`: on every session start, pulls the repo
     (`git pull --ff-only`, fails silently if it can't fast-forward)
     and surfaces this file's contents as context automatically.
   - `.claude/skills/shardic-sync/SKILL.md`: a manual `/shardic-sync`
     skill to run before ending a session — summarizes the session
     into a new dated entry here (newest on top), then auto-commits
     and pushes `notes.md` (no confirmation needed, per explicit
     user instruction when this was set up).
   - Found `.gitignore` blanket-ignored all of `.claude/`, which would
     have silently kept any of this from ever syncing. Narrowed it to
     just `.claude/settings.local.json`.

## State at end of session

- New skill isn't registered in *this* running session yet (the
  `.claude/skills/` directory didn't exist when this session started,
  so Claude Code's file watcher hasn't picked it up) — confirmed by
  `Skill(shardic-sync)` returning "Unknown skill". This very notes.md
  entry was written by manually following the SKILL.md steps instead,
  as an end-to-end logic test. Open `/hooks` or start a fresh session
  to get the skill and hook registered for real.
- Everything above is already committed and pushed (`fd85baf`); this
  entry itself will be committed/pushed as the last step of that
  manual test run.

## Possibly worth following up

- Once a fresh session picks up the skill, confirm `/shardic-sync`
  actually resolves as a slash command (this session could only prove
  the underlying logic, not the registration).
- `build_windows.bat` and the Windows side of the CI job remain
  unverified by a human on real Windows; the GitHub Actions
  `windows-latest` runner is the first real exercise of that path.

---

# Session notes — 2026-07-11

## What happened

The CI workflow (`build.yml`) had been sitting at the repo root as an
inert template — GitHub Actions never actually ran it because it
wasn't under `.github/workflows/`. This session:

- Moved it to `.github/workflows/build.yml` so it actually triggers.
- Fixed a bug in the Linux job: it built `VaultToolGUI-x86_64.AppImage`
  but never uploaded it as an artifact (only the CLI AppImage was).
- Added a `release` job: pushing a tag matching `v*` (e.g. `git tag
  v1.0.0 && git push --tags`) now runs the Windows + Linux builds and
  then publishes a GitHub Release named after the tag, with all four
  binaries attached (both `.exe`s, both AppImages) via `gh release
  create --generate-notes`.
- Plain pushes to `main` (no tag) still only build + upload
  workflow-run artifacts (`VaultTool-windows-x64`,
  `VaultTool-linux-x64`) — these expire and aren't versioned; no
  Release is created for ordinary pushes.
- Updated README to match: workflow path reference, and a new
  "publish a proper Release" subsection explaining the tag-push flow.

Commit: `d86e50a` — "Activate CI workflow and wire up tagged Releases"

## State at end of session

- Working tree had only binary diffs in the two local AppImage files
  (`VaultTool-x86_64.AppImage`, `VaultToolGUI-x86_64.AppImage`) —
  rebuild artifacts, not part of the commit.
- CI has not yet been observed running for real (workflow was just
  activated) — next push to `main` or `v*` tag push will be the first
  real test of both the build and release jobs.

## Possibly worth following up

- Verify the first live CI run actually succeeds end-to-end (both
  platforms build, artifacts upload correctly, and — when a tag is
  pushed — the release job finds and attaches all four files).
- `build_windows.bat` and the Windows side of the CI job remain
  unverified by a human on real Windows; the GitHub Actions
  `windows-latest` runner is the first real exercise of that path.
