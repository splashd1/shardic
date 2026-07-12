# Session notes — 2026-07-11 (shardic-prime)

## What happened

Confirmed the cross-machine sync setup from the prior entry works for
real this time — `/shardic-sync` resolved as a registered skill this
session (previously it only worked when manually walked through), and
the `SessionStart` hook correctly surfaced this file's prior entries
as context automatically.

Main work: designed and implemented **shardic-prime**, a new variant
of the vault scheme where one trustee (the "prime" trustee) is
mandatory at recovery time, on top of an otherwise plain
interchangeable k-of-n pool for the rest of the threshold. Explored
the existing `gf256_sss`/`vault_core` scheme first (byte-wise GF(256)
Shamir splitting a DEK; trustees hold codewords protecting opaque,
shuffled share records — see README's "How the design works"), then
proposed and built a layered construction: a random mask protects the
DEK directly for the prime trustee (a one-time pad, not a Shamir
share), while the masked DEK is split via the existing Shamir code
among the pool.

Implemented as a fully separate, additive variant (commit `54033f7`,
pushed):
- `gf256_sss_prime.py` — `split_secret_with_prime`/
  `reconstruct_secret_with_prime`, built on top of (imports, doesn't
  duplicate) `gf256_sss.py`'s field math.
- `vault_core_prime.py` — `create_vault_prime`/
  `match_codewords_prime`/`reconstruct_and_decrypt_prime`, reusing
  `vault_core.py`'s generic archive/KDF helpers via `import vault_core
  as base`.
- `vault_create_prime.py` / `vault_recover_prime.py` — CLI wrappers
  mirroring the base tools' UX and flags (`-T`/`-D` now count the
  prime trustee: 1 prime + T-1 pool, D = prime's codeword + D-1 pool
  codewords).
- Prime vaults are tagged `"scheme": "prime-trustee"` /
  `"container_format": "krypt1-prime"` so the two variants can't be
  cross-opened by mistake. Added a small guard to `vault_recover.py`
  (base tool) so it now cleanly refuses a prime vault instead of
  failing confusingly — the only change to any base-scheme file;
  `vault_core.py`/`gf256_sss.py` are untouched.
- Added a new README section ("shardic-prime: a mandatory prime
  trustee variant") explaining the construction and usage.

Verified end-to-end before committing: created a 1-prime + 3-pool
threshold-3 vault; confirmed two *different* pool subsets each
recovered correctly (proving pool interchangeability); confirmed all
3 pool codewords *without* the prime one never recover anything, both
via the CLI (hangs waiting for the prime, as designed) and directly
via `reconstruct_and_decrypt_prime` raising `VaultError`; ran a
regression pass confirming the base scheme's create/recover flow is
unaffected and that base vaults (no `scheme` key) leave the new guard
inert.

## State at end of session

- Commit `54033f7` pushed to `origin/main`. Working tree clean.
- Git author identity had to be set for this repo (local config only,
  per explicit user instruction — not global): `user.email
  splashd@gmail.com`, `user.name splashd`.
- shardic-prime is CLI-only; no GUI tab was added for it.

## Possibly worth following up

- GUI support for shardic-prime (a third tab in `vault_gui.py`) if
  that's wanted later — the core functions already exist in
  `vault_core_prime.py`, so it'd mostly be UI wiring.
- No automated test suite exists for either scheme (base or prime) —
  verification so far has been manual/ad hoc (both for the original
  build and for this session's shardic-prime work). Worth considering
  if this project keeps growing.

---

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
