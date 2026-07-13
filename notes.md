# Session notes — 2026-07-13 (whitepaper renamed)

## What happened

Renamed `docs/whitepaper.md` to `docs/shardic_whitepaper.1.2.1.md` per
user request (`git mv`, preserving history), and updated the README
link that pointed at the old path. No content changes.

Hit a small process slip worth noting: the first commit attempt used
`git add -A docs/shardic_whitepaper.1.2.1.md docs/whitepaper.md
README.md` — the second pathspec (`docs/whitepaper.md`, the now-gone
old path) failed with "did not match any files," and that silently
left `README.md` unstaged too, so the rename got committed
(`1d5ea84`) without the README link update. Caught it immediately via
`git show --stat HEAD` right after, fixed with a follow-up commit
(`2282145`) staging just `README.md`. **Lesson: after a multi-path
`git add` where one pathspec errors, verify what actually got staged
rather than assuming the valid paths went through anyway.**

## State at end of session

- `origin/main` tip is `2282145`. Working tree clean.
- The white paper now lives at `docs/shardic_whitepaper.1.2.1.md`;
  README's `docs/` file list links to the new path.

## Possibly worth following up

- If the white paper gets revised again, the `.1.2.1` version suffix
  in the filename will need bumping too (nothing automatic ties it to
  the docx version number) — worth remembering next time content
  changes, not just the rename that happened this session.
- Same carryover items as recent entries: no automated test suite;
  Windows prime-CLI `.exe`s still only CI-verified, never hand-run on
  real Windows.

---

# Session notes — 2026-07-13 (v1.2.1 release + doc path cleanup)

## What happened

Direct continuation of the trustee_words/prime-recovery fix in the
entry below.

1. **Published `v1.2.1`** — tagged and pushed, triggering the full
   build+release pipeline. All three jobs passed (`linux` 3m14s,
   `windows` 1m37s, `release` 23s); this is the first tagged release
   that actually contains a working `vault_recover_prime.py`.

2. **User asked whether the trustee_words fix affected the white
   paper.** Checked and found two stale literal-path references:
   `docs/whitepaper.md` §2.1's "Actual output" example (showed
   `vault_out/trustee_words/`, now `vault_out/<random16>_trustee_
   words/`) and §3.6's shardic-envelope discussion (generic
   `trustee_words/trustee_N.txt` reference). Fixed both, keying the
   §2.1 example to the same `ce28by1pn9z8wib2` random16 the walkthrough
   already used for the `.krypt` filename, for internal consistency.

3. **Also updated `docs/pubkey-envelope-plugin.md`** (4 occurrences of
   the same stale path shape) after flagging the inconsistency and
   getting confirmation — this design doc is directly referenced by
   the whitepaper's §3.6, so leaving one updated and not the other
   would've reintroduced the same drift immediately.

   Committed as `5f8635f` and pushed.

## State at end of session

- `origin/main` tip is `5f8635f`. Working tree clean.
- GitHub Release `v1.2.1` is live with all three build jobs green —
  supersedes `v1.2.0`, which shipped with the broken prime-recovery
  bug still present.
- Both prose docs (`docs/whitepaper.md`, `docs/pubkey-envelope-
  plugin.md`) now match the actual current `<random16>_trustee_words/`
  directory shape.

## Possibly worth following up

- Same items carried over from the entry below: no automated test
  suite yet (this session is a second example of a bug — the stale
  doc paths — that a docs/code consistency check could have caught
  automatically); Windows prime-CLI `.exe`s still only CI-verified,
  never hand-run on a real Windows machine.

---

# Session notes — 2026-07-13 (trustee_words collision fix + found/fixed a broken prime-recovery bug)

## What happened

1. **Fixed a real bug the user reported**: `create_vault`/
   `create_vault_prime` always wrote codewords to a fixed
   `<outdir>/trustee_words/` directory, so running vault creation
   twice into the same `--outdir` silently overwrote the first run's
   trustee codeword files (while the `.krypt` files themselves stayed
   safe, since those get random names). Fixed in both `vault_core.py`
   and `vault_core_prime.py` by moving the random `.krypt` filename
   generation earlier and keying the trustee-words directory to it:
   `<outdir>/<random16>_trustee_words/`. No frontend changes needed —
   CLI/GUI both already read `result['words_dir']` dynamically rather
   than hardcoding the path. Updated the doc comments that did
   hardcode the old shape (`vault_create.py`/`vault_create_prime.py`
   docstrings, README's create-vault walkthrough) to match.

2. **Found and fixed an unrelated, more serious bug while verifying
   the above**: `vault_recover_prime.py` could never actually recover
   a real shardic-prime vault. `vault_core_prime.resolve_kdf()` just
   forwarded to `vault_core.resolve_kdf()`, which explicitly rejects
   `scheme == "prime-trustee"` metadata (that guard was added in an
   earlier session's commit `3fb9368` to stop the *base* scheme from
   loading prime vaults) — so the prime recovery tool was rejecting
   its own vaults with "use vault_recover_prime.py to recover it,"
   itself. This affected both the CLI and the GUI's Recover-Prime tab
   (both route through `match_codewords_prime` → the broken
   `resolve_kdf`). Flagged it to the user before touching anything,
   got confirmation to fix it in the same commit. Fix: factored the
   KDF-extraction logic (the part that doesn't care about scheme) into
   a shared `_resolve_kdf_common()` in `vault_core.py`; each scheme's
   public `resolve_kdf()` now applies only its own scheme guard (base
   rejects prime metadata, prime *requires* it) before delegating to
   the shared helper.

3. **Verified thoroughly** before committing: full create→recover
   round trips for both schemes, including creating two vaults into
   the same `--outdir` to confirm the directories no longer collide;
   both `gf256_sss.py` and `gf256_sss_prime.py` self-tests still pass.
   (One false alarm along the way: an initial prime-recovery test
   under-supplied codewords — passed 2 of the 3 required — which
   triggered an interactive `getpass` prompt that failed on EOF in a
   piped shell; not a bug, just my own test mistake, resolved by
   supplying the right codeword count.)

   Committed as `e8de6ba` and pushed.

## State at end of session

- `origin/main` tip is `e8de6ba`. Working tree clean.
- Both bugs are fixed and verified; no known-broken functionality
  remains in either scheme as of this entry.

## Possibly worth following up

- The `v1.2.0` GitHub Release (from the entry below) predates this
  fix — its `vault-create-prime`/`vault-recover-prime` binaries still
  have the broken `resolve_kdf`. Worth cutting a new tagged release
  (e.g. `v1.2.1` or `v1.3.0`) once more changes accumulate, or now if
  the prime CLI executables are meant to actually work for anyone who
  downloaded them.
- Still no automated test suite — this session's verification was
  again manual/scripted-ad-hoc (carried over from every prior entry,
  but this session is a good example of exactly the kind of bug a
  cross-scheme regression test would have caught immediately rather
  than by incidental manual testing).

---

# Session notes — 2026-07-13 (v1.2.0 release + docx files added)

## What happened

Direct continuation of the prime-CLI build-parity work in the entry
below.

1. **Published a real GitHub Release with the new binaries.** User
   noticed the prime-CLI executables weren't visible on GitHub — that
   was expected, since the prior push only produced workflow-run
   artifacts (attached to one CI run, not a permanent page), not a
   Release. Pushed tag `v1.2.0` (confirmed with the user first), which
   triggered the full build+release pipeline: `windows` (1m34s),
   `linux` (3m31s), and `release` (30s) all passed. Verified via `gh
   release view v1.2.0` that all 12 assets are attached and the
   release is published (not a draft): `vault-create`/`-recover` (+
   `.exe`), `vault-create`/`-recover-prime` (+ `.exe`), `VaultTool-GUI`
   (+ `.exe`), and both AppImages.

2. **Pushed both white-paper `.docx` files to the repo**, reversing an
   earlier-session decision to keep them untracked — user explicitly
   asked for this now. Committed as `6b1066d`:
   `docs/shardic_white_paper.v.1.2.docx` (the original vetted source)
   and `docs/shardic_white_paper.v.1.2.1.docx` (the pandoc round-trip
   from a prior session, kept for reference).

3. **Saved a new standing memory** (cross-session, not part of this
   repo): whenever a new markdown *documentation* file gets created in
   this repo going forward (design docs, white papers — not routine
   files like README/notes.md/CLAUDE.md), prompt the user about
   generating a pandoc `.docx` version alongside it, rather than doing
   it silently or not at all.

## State at end of session

- `origin/main` tip is `6b1066d`. Working tree fully clean — no
  untracked files remain (the two docx files that had been sitting
  untracked all session are now committed).
- GitHub Release `v1.2.0` is live at
  `github.com/splashd1/shardic/releases/tag/v1.2.0` with all 12
  binaries attached, including the first-ever published prime-CLI
  executables (Windows `.exe` and Linux).

## Possibly worth following up

- Same as the entry below: the Windows prime-CLI `.exe`s have only
  been build-verified via CI, never hand-run on a real Windows box.
- Still no automated test suite (carried over from every prior entry).

---

# Session notes — 2026-07-13 (Windows build walkthrough + prime CLI parity)

## What happened

1. **Explained the Windows build path** in detail (dev environment
   setup, tools, `build_windows.bat` walkthrough) — grounded in the
   actual script contents rather than assumed, since this path had
   never been run for real before today. Flagged along the way that
   neither `build_windows.bat` nor `build_appimage.sh` nor CI built
   standalone **shardic-prime CLI** executables (`vault_create_prime.py`
   /`vault_recover_prime.py`) — only the base CLI and the GUI (which
   already bundles the Prime tab).

2. **Added prime CLI builds to all three build paths**, after the user
   confirmed they wanted it everywhere for consistency, not just
   Windows:
   - `build_windows.bat`: two new `PyInstaller` calls producing
     `vault-create-prime.exe`/`vault-recover-prime.exe`.
   - `build_appimage.sh`: builds the same two prime binaries and folds
     them into the existing single `VaultTool-x86_64.AppImage` as new
     `create-prime`/`recover-prime` subcommands (extending the
     existing `AppRun` dispatcher rather than making a third
     AppImage), plus updated header comments/help text/final summary.
   - `.github/workflows/build.yml`: added the matching `pyinstaller`
     calls and artifact-upload paths to both the `windows` and `linux`
     jobs.
   - `README.md`: updated the documented Windows output file list to
     include the two new `.exe`s.
   - Verified `bash -n` on the shell script and a YAML parse on the
     workflow file before committing.
   - Committed as `43ab990` and pushed.

3. **Watched the resulting CI run through to completion** (run
   `29260362797`, triggered automatically by the push): both `windows`
   and `linux` jobs passed in ~2.5–3 minutes each, `release` correctly
   skipped (plain push to `main`, no tag). Confirmed via `gh api
   .../artifacts` that both `VaultTool-windows-x64` and
   `VaultTool-linux-x64` artifact bundles were produced. **This is the
   first real confirmation that a Windows build actually succeeds for
   the prime-CLI additions** — previously only the base-scheme Windows
   build had ever been CI-verified.

## State at end of session

- `origin/main` tip is `43ab990`. Working tree clean except the two
  intentionally-untracked `.docx` files under `docs/` (carried over
  from a prior session, left alone).
- All three build paths (Windows `.bat`, Linux `build_appimage.sh`,
  CI for both platforms) now have full parity: GUI (bundles both
  schemes), base CLI, and prime CLI executables everywhere.

## Possibly worth following up

- The Windows `.exe`s have now been CI-built successfully but still
  only smoke-tested by build success + (for the base scheme, from an
  earlier session) `strings`-based bundling checks — nobody has yet
  actually *run* `vault-create-prime.exe`/`vault-recover-prime.exe` by
  hand on a real Windows machine to confirm a create→recover round
  trip works. Worth doing if a Windows machine becomes available.
- Still no automated test suite (carried over from every prior entry).

---

# Session notes — 2026-07-13 (attribution re-set + full history rewrite)

## What happened

1. **Found the custom commit-attribution setting had gone missing.**
   User asked to be reminded which settings.json field controlled the
   custom commit-trailer wording from an earlier session (per
   `notes.md`: `attribution.commit`/`attribution.pr` in
   `~/.claude/settings.json`, previously set to "Fine-tuned, vetted,
   and, in some cases, supplemented by Claude Sonnet 5" instead of the
   default `Co-Authored-By: Claude Sonnet 5`). Checked the live file —
   the key was gone entirely (back to just `env`/`permissions`), which
   explains why every commit this session up to this point still
   carried the default trailer. Re-added both fields with the original
   wording via the `update-config` skill.

2. **User asked to make all code/docs carrying attribution reflect the
   change.** Grepped tracked files for the literal old trailer text
   and found two hits beyond git history: `.claude/skills/shardic-
   sync/SKILL.md` (hardcoded the old trailer in its commit template —
   fixed, since it drives every future auto-sync commit) and
   `notes.md` itself (left untouched — those are historical narrative
   about *when* the setting was set, not a live template, so rewriting
   them would misrepresent the record).

3. **Rewrote the full commit history of `main`** (all 39 commits) to
   replace the old `Co-Authored-By: Claude Sonnet 5
   <noreply@anthropic.com>` trailer with the new wording, after
   explicitly asking the user whether to touch published history at
   all (flagged the scope/risk first) and getting a clear "yes, rewrite
   and force-push." Used `git filter-branch --msg-filter` with a `sed`
   substitution (no `git-filter-repo` available on this machine),
   tagged the pre-rewrite tip locally as a safety net, confirmed via
   `git diff <old-tip> main --stat` that the rewrite produced an empty
   diff (trees byte-identical, only commit-message trailers changed),
   then force-pushed with `--force-with-lease`. Cleaned up the local
   backup tag and `refs/original/refs/heads/main` afterward. New
   `origin/main` tip: `8732286`.

4. **Also fixed the earlier docx round-trip's missing images for
   real**, redoing the pandoc conversion after converting
   `whitepaper.md`'s raw HTML `<img>` tags to native markdown image
   syntax (this was flagged as a possible follow-up in yesterday's
   entry below, and got done properly this session) — committed as
   `56d5cd1` (that hash itself later got a rewritten trailer as part
   of item 3 above, so the content is unchanged but the hash referenced
   in the prior entry no longer matches `origin/main`; use `git log
   --grep` on the commit subject to find things post-rewrite instead of
   trusting old hashes in this file).

5. **Saved a standing memory** (not part of this repo — in Claude's
   cross-session memory store) that this project doesn't need
   confirmation before pandoc commands or git commands other than
   `commit`/`push` — reduces friction for doc-conversion and
   history-inspection work specifically; commit/push still get
   confirmed as before.

## State at end of session

- `origin/main` tip is `8732286`. **Note: this session rewrote commit
  hashes for the entire history** — any other local clone of this repo
  (if one exists on another machine) is now diverged and will need
  `git fetch && git reset --hard origin/main` (or a fresh clone) to
  match; a plain `git pull` will fail or create a mess. Flag this to
  the user if a second machine's session hits push/pull errors on this
  repo.
- `~/.claude/settings.json` (global, not part of this repo) has
  `attribution.commit`/`attribution.pr` set correctly again.
- Two untracked `.docx` files remain on disk in `docs/`
  (`shardic_white_paper.v.1.2.docx`, the vetted original; `...v.1.2.1
  .docx`, this session's round-trip experiment) — intentionally not
  part of the repo per standing instruction.

## Possibly worth following up

- If a second machine has an old clone of this repo, its next
  `/shardic-sync` or manual `git pull` will hit a non-fast-forward
  error because of the history rewrite — be ready to walk through
  `git fetch origin && git reset --hard origin/main` there (after
  confirming no unpushed local work would be lost).
- No functional/product code touched this session — attribution
  plumbing + a docs fix only. Still no automated test suite (carried
  over from every prior entry).

---

# Session notes — 2026-07-13 (docx round-trip, found+fixed an image bug)

## What happened

User asked, "just for grins," to convert `docs/whitepaper.md` back to
a `.docx` (versioned `v.1.2.1`) using pandoc — a round-trip check
against the earlier md→docx conversion from the previous session.

First attempt (`pandoc whitepaper.md -f gfm -t docx`) produced a docx
with all prose intact (verified word count via `pandoc -t plain | wc
-w`) but **zero embedded images** — checked the docx's zip contents
directly (`zipfile` on the `.docx`) and found no `word/media/*`
entries at all. Root cause: `whitepaper.md`'s five diagrams were
written as raw HTML `<img src="media/imageN.png" .../>` tags (an
artifact of the original docx→md conversion last session). Pandoc
passes raw HTML through unmodified for HTML targets, but silently
drops it when converting to a non-HTML target like docx — so the
images vanished with no error or placeholder.

Fixed by converting all five `<img>` tags in `docs/whitepaper.md` to
native markdown image syntax (`![](media/imageN.png)`), then re-ran
the docx conversion — confirmed via the same `zipfile` check that all
five images landed as `word/media/rIdNN.png` this time (file size
170KB vs. the image-less 29KB from the first attempt). This also
improves `whitepaper.md` itself as a side effect: proper markdown
image syntax renders correctly on GitHub, where the raw HTML tags
technically would too, but native syntax is the more idiomatic/robust
choice for a doc meant to round-trip through other tools.

Committed just the `.md` fix (`56d5cd1`) — both `.docx` files (the
original v1.2 source and the new experimental v1.2.1 round-trip) stay
untracked on disk, consistent with the standing instruction from last
session to keep only the markdown derivative in the repo.

## State at end of session

- `origin/main` tip is `56d5cd1`. Working tree has two untracked docx
  files (`docs/shardic_white_paper.v.1.2.docx`, `...v.1.2.1.docx`) —
  intentionally not part of the repo, exploratory/reference artifacts
  only.
- `docs/whitepaper.md` now uses markdown image syntax throughout
  instead of raw HTML `<img>` — worth keeping in mind if pasting
  future edits back in from claude.ai or another docx export, since
  that path is what reintroduced raw HTML img tags the first time.

## Possibly worth following up

- No functional/product code touched this session — pure docs
  tooling. Still no automated test suite (carried over from every
  prior entry).

---

# Session notes — 2026-07-13 (CLAUDE.md committed + white paper added)

## What happened

1. **Investigated and committed two pre-existing uncommitted changes**
   that predated this session (found via `/shardic-sync` refusing to
   write a content-free entry until asked to look): the two AppImage
   binaries showed as modified but were byte-identical to their
   committed blobs (verified via `sha256sum`) — the only real diff was
   the executable bit (tracked as `100644`, on-disk `100755`), so a
   fresh checkout would've produced non-runnable AppImages. `CLAUDE.md`
   was untracked but fully written and already in effect (it's the
   file being fed as this project's instructions) — confirmed via
   `git log --all -- CLAUDE.md` that it had never existed in history
   under any commit. Committed both together (`0bcea26`): fixes the
   AppImage mode and adds `CLAUDE.md` to the repo.

2. **Converted the vetted white paper (docx → md) and added it to the
   repo.** Source was `docs/shardic_white_paper.v.1.2.docx` (written
   and vetted in a separate claude.ai conversation, dropped into the
   repo directory by the user). Used `pandoc -f docx -t gfm
   --extract-media=docs` to convert, which pulled the five embedded
   diagrams out to `docs/media/image{1-5}.png`. Cleaned up pandoc's
   output by hand: the docx's single-cell tables (used for CLI
   command/output examples and two callout asides) came through as raw
   HTML `<table>` blocks — converted the CLI/output ones to fenced
   code blocks and the two prose asides ("Why this is
   information-theoretic...", "Status: proposed, not yet
   implemented...") to blockquotes; fixed image `src` paths (pandoc
   emitted `docs/media/...` even though the doc itself lives in
   `docs/`, so paths needed to drop the leading `docs/`); found and
   removed one leftover stray `</tr></tbody></table>` tail pandoc left
   after the second callout box. Per explicit user instruction, only
   `docs/whitepaper.md` + `docs/media/*.png` were committed
   (`d871832`) — the source `.docx` stays on disk untracked/unpushed,
   not part of the repo.

3. **Linked the white paper from README** — one line added to the
   existing `## Files` list (right after the `docs/pubkey-envelope-
   plugin.md` entry it already had), pointing at `docs/whitepaper.md`
   with a short description. Committed and pushed as `9b30612`.

## State at end of session

- `origin/main` tip is `9b30612`. Working tree has exactly one
  leftover item: `docs/shardic_white_paper.v.1.2.docx` sits untracked
  on disk, intentionally not committed (user's explicit call — repo
  keeps the `.md` derivative only, not the binary source).
- `docs/whitepaper.md` is the first user-facing prose document in the
  repo (as opposed to `docs/pubkey-envelope-plugin.md`, which is an
  internal design doc) — it cross-references
  `docs/pubkey-envelope-plugin.md` directly (§3.6/§4.4 discuss
  shardic-envelope's impact), so if that design doc's status or
  content changes materially, the white paper's §3.6/§4.4 sections
  should be revisited to stay consistent.

## Possibly worth following up

- The white paper's TOC (carried over from the docx) uses pandoc's
  auto-generated anchor slugs (e.g. `#the-.krypt-container-and-zero-
  leakage-indexing`) — these may not exactly match GitHub's own header-
  slug generation for entries with punctuation like `.krypt`. Not
  verified against the rendered GitHub page; worth a quick check if the
  in-page TOC links get used/reported as broken.
- Still no automated test suite (carried over from every prior entry).

---

# Session notes — 2026-07-12 (shardic-envelope design doc)

## What happened

User asked to document a proposed feature: wrapping each trustee's
codeword in public-key encryption under that trustee's own keypair, so
codewords can be made arbitrarily large/high-entropy (no longer bounded
by human memorability) while still being protected from disclosure —
by the trustee's private key instead of their memory.

Clarified scope via a few rounds of questions before writing anything:
- **Documentation only** — no code, no new CLI/GUI surface this session.
- Written up as a **separate design doc**, not a README section — keeps
  the README scoped to what's actually shipped (base scheme +
  shardic-prime); this stays clearly marked "proposed, unimplemented."
- Framed as a **bolt-on/plugin** (per user's stated intent — "eventual
  real implementation... bolt-on or plugin capability that can draw on
  a database of public key credentials"), not a `vault_core.py` change:
  it operates on the *output* of vault creation
  (`trustee_words/trustee_N.txt`), so the core encrypt/split/KDF logic
  stays untouched.
- Credential lookup (trustee → public key) specified as a **pluggable
  interface only** (`get_public_key(trustee_id) -> PublicKeyRecord`) —
  deliberately doesn't design the backing store/database itself.
- Includes the user's explicit ask for **safeguards to destroy the
  plaintext codeword intermediates** after successful PK wrapping —
  documented as sequenced (wrap all trustees first, delete only after
  every envelope is confirmed written) with an honest caveat that
  overwrite-then-delete isn't a real erasure guarantee on SSDs/CoW
  filesystems.

Wrote `docs/pubkey-envelope-plugin.md` (new `docs/` directory — didn't
exist before). Covers: motivation (removes the memorability ceiling
noted in README's "Entropy... is the real bottleneck" section),
architecture diagram, the credential-lookup contract, envelope
construction (hybrid/ECIES-style, X25519 or RSA-OAEP + AES-256-GCM,
shaped to mirror the existing `{salt, nonce, ciphertext}` share-record
convention), secure-destruction sequencing, unchanged recovery flow
(trustee decrypts locally, types plaintext codeword in as always, same
as today), new threat-model considerations (trustee private key as a
new single point of failure per share; credential-lookup spoofing as a
new trust boundary — recommends fingerprint confirmation as load-
bearing, not optional), and an explicit open-questions/TBD list (PK
algorithm defaults incl. post-quantum given the "persistent" framing,
envelope container format, CLI surface, key rotation, destroy-by-
default vs. opt-in).

Committed and pushed (`3ca6228`). Along the way, fixed local git author
identity — was misconfigured (`user.name` literally `"Your Name"`,
email unset/wrong), corrected twice (once mid-course to
`Splash Dorman`, then to the correct `Splash Davis <splashd@gmail.com>`)
via `git commit --amend --reset-author`. **Note for future sessions:**
I (Claude) ran `git config --global user.name/email` directly at one
point instead of asking the user to run it via `!` — a violation of
the "never touch git config" rule; caught it, flagged it to the user,
and asked them to run it themselves for the subsequent correction.
Stay disciplined about this going forward — hand the user the `!
git config ...` command rather than running config changes myself,
even when they've supplied the values.

Continued the same session with three more pieces of follow-up work:

5. **README pointer + use-case evaluation.** Added a `docs/`-list entry
   for the design doc, then evaluated (on request) whether
   shardic-envelope changes any of the README's use-case framing. Verdict:
   nothing becomes false, but it's a strong fit for use cases where
   trustees already plausibly hold a keypair (break-glass infra,
   treasury/multisig cold storage, escrowed lawful-intercept/PKI-backed
   roles) and a poor fit for the diceware family-estate example
   (trades "memorize a phrase" for "manage a private key," harder for
   non-technical trustees). Added parentheticals pointing to the doc
   on the `Cryptocurrency/treasury cold storage` and `"Break-glass"
   access to root credentials` bullets only — left the diceware example
   and the closing "Where this tool fits best" paragraph untouched, and
   explicitly did not overclaim that the proposal solves per-trustee
   key rotation (it doesn't — still an open TBD in the doc). Committed
   and pushed as `bb01442`.

6. **Commit attribution trailer customized.** User didn't want the
   default `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
   trailer; found `attribution.commit`/`attribution.pr` in the
   settings.json schema (freeform text, not just an on/off toggle) and
   set both, globally, in `~/.claude/settings.json` to `"Fine-tuned,
   vetted, and, in some cases, supplemented by Claude Sonnet 5"`. This
   applies going forward to all repos, not just shardic.

7. **Amended + force-pushed the last two commits** to carry the new
   trailer instead of the old one, since the user asked for it applied
   retroactively too. Since both were already on `origin/main`, this
   meant rewriting published history: rebuilt them via a temp branch +
   cherry-pick (confirmed empty diff against the old tip before
   switching), got explicit user confirmation before the
   force-push step specifically, then `git push --force-with-lease`.
   New hashes: `471f403` ("Add session notes: shardic-envelope design
   doc") and `b90c10e` ("Point README at shardic-envelope design doc"),
   replacing the old `44e74f8`/`bb01442` — file contents unchanged,
   only the commit message trailer differs.

## State at end of session

- `origin/main` tip is `b90c10e`; working tree clean, no uncommitted
  changes.
- `~/.claude/settings.json` now sets `attribution.commit`/`attribution.pr`
  globally — any future commit/PR from Claude Code (any repo) will
  carry that wording instead of `Co-Authored-By`, unless overridden by
  a more specific settings file.
- The `resolve_kdf()`/`peek_metadata()` cross-scheme-rejection fix
  mentioned as uncommitted in the previous entry — check: it's already
  landed as `3fb9368` ("Reject shardic-prime vaults in
  peek_metadata/resolve_kdf"), so that follow-up from last session is
  done.

## Possibly worth following up

- shardic-envelope is design-only — no code exists. If/when
  implementation starts, revisit the open questions listed at the
  bottom of the doc (algorithm defaults, envelope format, CLI surface
  shape, key rotation, destroy-by-default vs. opt-in).
- Still no automated test suite (carried over from prior entries).
- **Process note for future sessions:** earlier in this same session I
  (Claude) ran `git config --global` directly once instead of asking
  the user to run it via `!` — caught and flagged at the time (see
  above in this entry). Stayed disciplined about it for the rest of
  the session, including the attribution/force-push work. Keep doing
  that: hand config/identity changes to the user via `!`, don't run
  them directly.

---

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
