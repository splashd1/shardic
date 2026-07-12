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
