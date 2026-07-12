# Session notes — 2026-07-12 (raised defaults + GUI testing spree)

## What happened

Started from a cryptographic-strength discussion (recap of codeword
modes/entropy, then a deep-dive on reconciling human-memorable
codewords against "NSA-grade" strength — landed on: split-knowledge
(the existing `D`-of-`T` threshold) is the actual real-world answer,
not cramming more entropy into one human's memory).

1. **Raised the actual defaults** (commit `3401fb2`): memorable mode
   now defaults to 8 words (~103 bits, up from 5/~65) and Argon2id
   defaults moved to `time_cost=4`/`memory_cost=256 MiB` (up from
   3/64 MiB), in both CLIs and `vault_core.resolve_word_mode()`/`kdf.py`.
   Added a "Customize Argon2id cost (advanced)" checkbox to both GUI
   Create tabs — unchecked by default (hidden fields, raised defaults
   apply), checking it reveals time/memory/parallelism entry fields
   pre-filled with the defaults and freely overridable, wired through
   `vault_core.resolve_kdf_params`. README updated throughout.

2. **Found and fixed a real GUI bug** (commit `fcbd352`): all four
   background-worker error handlers (`CreateTab`/`RecoverTab` ×
   base/prime) deferred error reporting via
   `self.after(0, lambda: ...str(e)...)`, but Python deletes an
   `except ... as e` variable when the block exits — so by the time the
   deferred lambda ran, `e` was gone and it raised `NameError` instead
   of ever showing the error dialog. Real-world impact: wrong/missing
   codewords (or any create/recover failure) produced *no* feedback at
   all — button just stayed disabled forever. Fixed by capturing the
   message into a plain local var before scheduling the callback.
   Found via headless GUI testing (Xvfb + a venv with `argon2-cffi`,
   driving the real Tkinter widgets/mainloop, not just unit-testing the
   core logic).

3. **Extensive headless GUI regression testing** across both sessions'
   worth of changes: widget mechanics (memorable/strong-words mutual
   exclusion, field enable/disable, Argon2 checkbox show/hide),
   synchronous validation errors, the async error-dialog paths above
   (both exception branches), and full create→recover round trips in
   several modes (memorable, synthetic+strong-words, shardic-prime with
   shuffled codeword order). All via disposable venvs + `xvfb-run`,
   cleaned up after each run — never left in the repo.

4. **Found and fixed a second real bug** (uncommitted as of end of
   session — see below): `vault_core.peek_metadata()` had no
   `scheme` check, so the GUI's base `RecoverTab` would silently accept
   a shardic-prime `.krypt` at load time (unlike `RecoverPrimeTab`,
   which correctly refuses a base-scheme vault). It always failed safe
   in practice (GF(256)'s duplicate-x-coordinate guard catches it) but
   with a confusing internals error instead of a clear rejection. Note:
   initially over-claimed this also affected the CLI — it doesn't,
   `vault_recover.py` already had its own separate scheme guard in
   `main()` that I'd missed on first read. Fix adds the same check to
   both `peek_metadata()` (GUI load-time rejection, matching the prime
   tab's UX) and `resolve_kdf()` (the actual shared choke point for
   `match_codewords()`/CLI, as defense-in-depth). Verified: CLI
   (already worked), `peek_metadata`, `resolve_kdf`, and GUI `on_load`
   all now reject cleanly; normal recovery unaffected.

## State at end of session

- `3401fb2` and `fcbd352` pushed to `origin/main`.
- **`vault_core.py` has an uncommitted fix** (the `peek_metadata`/
  `resolve_kdf` scheme-check addition from item 4) — user hadn't yet
  said "commit this" when the session ended on a sync request. Next
  session: confirm and commit if still wanted.
- No other working-tree changes; all test venvs/vaults were scratch
  and cleaned up.

## Possibly worth following up

- Still no automated test suite — everything this session was
  scripted ad-hoc headless GUI testing (Xvfb + throwaway venvs),
  same gap noted in prior entries. This session in particular found
  two real bugs that unit tests on `vault_core`/`vault_core_prime`
  alone wouldn't have caught (both were GUI-layer/integration issues),
  which is a decent argument for at least a headless-GUI test script
  living in-repo rather than being reinvented each session.
- The cross-scheme fix touched `resolve_kdf()`, which is also called
  by `vault_recover.py` directly — worth double-checking nothing else
  depends on `resolve_kdf()` *not* raising for prime metadata before
  that commit lands.

---

# Session notes — 2026-07-12 (gh auth setup)

## What happened

Logged the local `gh` CLI into GitHub (device-code web flow) as
account `splashd1` and confirmed full read/write access to
`splashd1/shardic` (`viewerPermission: ADMIN`). Along the way found
and fixed two auth/config gaps that would've blocked pushes going
forward: local git had no `user.name`/`user.email` configured (set to
`splashd1` / `splashd@gmail.com`), and git wasn't wired to use `gh`'s
stored credentials for HTTPS push (`gh` had a valid token but `git
push` still failed with "could not read Username" until running `gh
auth setup-git`). Verified the full chain end-to-end by pushing a
throwaway test commit (`.gh-auth-test.txt`) to `main` and confirming
it via `gh api repos/splashd1/shardic/commits/main`, then reverted it
with `git revert` on request — working tree is clean, no trace left
except the add+revert pair in history.

## State at end of session

- `gh auth status` shows logged in to github.com as `splashd1`, token
  scopes `gist, read:org, repo`.
- Local git identity and credential helper are now correctly
  configured for this repo — future pushes should just work without
  re-auth.
- Working tree clean; nothing else changed this session.

---

# Session notes — 2026-07-12 (build verification + --memorable)

## What happened

Two things this session, continuing from shardic-prime work below:

1. **Built and verified the AppImage + Windows exe for real**, to
   actually test the Shardic-Prime GUI tab rather than just the raw
   `.py` source. Linux AppImage built locally (`build_appimage.sh`);
   Windows `.exe` built via a real `windows-latest` GitHub Actions
   runner, triggered with `gh workflow run build.yml` (no new
   commit/tag needed — `workflow_dispatch` is wired up). Confirmed via
   `strings` (after extracting the AppImage's squashfs) that the
   shardic-prime GUI classes are actually bundled into both packaged
   binaries, not just present in source. Artifacts landed in `dist/`
   (untracked, left alone per explicit user instruction — not meant to
   be committed). Also found and removed a stray `vault_20260712T042010Z/`
   test vault that appeared at the repo root while the AppImage was
   open on the user's real screen (`DISPLAY=:0`) — looked like the
   user testing "Create Vault" live with default settings; removed at
   their request. Committed the incidental `chmod +x` on
   `build_appimage.sh` separately (`bfcd5f4`) since the user said to
   allow that mode change.

2. **Added `--memorable` codeword mode and made it the new default**
   (commit `9124820`), following a design discussion: whole, real
   dictionary words (bundled EFF wordlist, embedded as a Python tuple
   in the new `eff_wordlist_words.py` rather than read from the `.txt`
   at runtime — necessary so it actually works in the frozen
   `.exe`/AppImage builds, since PyInstaller onefile doesn't bundle
   loose data files) instead of synthetic pronounceable syllables.
   Omitting `--word-length` (previously a hard argparse error) now
   triggers memorable mode by default in both `vault_create.py` and
   `vault_create_prime.py`, via a shared `vault_core.resolve_word_mode()`
   helper; passing `--word-length` still gets the exact old behavior
   (full backward compat). `--memorable` and `--strong-words` are
   mutually exclusive (opposite goals). Added a matching "Memorable
   codewords" checkbox (checked by default) to both GUI Create tabs,
   with live mutual-exclusion against Strong Words and the
   now-irrelevant codeword-length field. Verified via full CLI
   create→recover round trips (memorable default, explicit
   `--word-length` regression, the conflict error, shardic-prime
   variant) and by driving the actual GUI widget handlers under a real
   Tk mainloop.

## State at end of session

- Working tree clean; `9124820` (and `bfcd5f4` before it) pushed to
  `origin/main`.
- `dist/` (local AppImage + Windows exe build output) is untracked and
  intentionally left that way.

## Possibly worth following up

- Still no automated test suite for any of this (base scheme,
  shardic-prime, memorable mode) — all verification has been manual/
  scripted-ad-hoc in-session across several sessions now. Worth a real
  test suite if this keeps growing.
- The Windows `.exe` has only been smoke-tested via CI build success +
  `strings` bundling checks, never actually run by a human on real
  Windows.

---

# Session notes — 2026-07-11 (shardic-prime GUI)

## What happened

Added GUI support for shardic-prime (follow-up to the prior entry,
which shipped it CLI-only). `vault_gui.py` now has a third top-level
tab, "Shardic-Prime", containing its own Create/Recover sub-tabs
(`CreatePrimeTab`/`RecoverPrimeTab`) built as an inner `ttk.Notebook`
inside a `ShardicPrimeTab` container. They drive `vault_core_prime`
the same way the CLI scripts do, reusing the existing
background-thread + log-queue pattern from `CreateTab`/`RecoverTab`
verbatim (no changes to the base tabs). Recover's codeword entry
fields accept codewords in any order, matching the CLI's behavior —
which one is the prime trustee's is only discovered once it decrypts.

Verified by actually building and rendering the widget tree under a
real Tk `mainloop()` (not just a syntax check), then driving a full
create → recover cycle through the real button handlers
(`on_create`/`on_recover`) with two different pool-codeword subsets,
confirming both interchangeability and correct recovery end-to-end.
An initial test attempt using manual `root.update()` polling instead
of `mainloop()` threw `RuntimeError: main thread is not in main loop`
from the worker thread's `self.after(...)` callback — a test-harness
artifact (Tkinter's cross-thread `after()` needs a real mainloop
running), not an app bug; the actual crypto work had already
completed correctly in both runs regardless.

README updated: GUI section now documents three tabs; the file
listing no longer says shardic-prime is CLI-only.

Committed and pushed as `870915d`.

## State at end of session

- Working tree clean, `870915d` pushed to `origin/main`.
- shardic-prime now has full parity between CLI and GUI frontends.

## Possibly worth following up

- Still no automated test suite for either scheme — all verification
  (base scheme originally, shardic-prime CLI, shardic-prime GUI) has
  been manual/scripted-ad-hoc in-session. Worth a real test suite if
  this keeps growing.

---

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
