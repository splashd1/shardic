# Threshold-Recoverable Encrypted Vault

Two CLI programs, a GUI, and shared library modules.

This tool gives an operator the ability to encrypt data such that
exposure is entrusted to a defined pool of T trustees, requiring a
minimum subset of D of them to actively agree — each by supplying
their individual codeword — before the plaintext can be recovered.
No single party, including whoever created the vault, can decrypt it
alone; any group smaller than D learns nothing about the data even if
they pool what they have (see "How the design works" below).

**Example: break-glass access to critical infrastructure.** A company
locks a root CA private key, a production database master key, or a
SCADA override credential in a vault with, say, `T=7` trustees (a mix
of senior engineers, security officers, and an executive) and a
`D=4` threshold. Day to day, nobody has access to the key at all — it
only gets reconstructed for a genuine emergency (an incident, an
outage, an urgent access-revocation). When that happens, no single
person, including whoever's holding the `.krypt` file, can unlock it
unilaterally: four of the seven trustees each have to independently
choose to supply their codeword. That gives the organization a
credential that's recoverable under real emergency conditions while
staying resistant to misuse by any one insider or one compromised
account — with a built-in record of exactly which trustees
participated in each recovery.

**Example: diceware-style memorable codewords.** A family estate plan
splits access to a password manager's master vault among five
relatives (`T=5`, `D=3`) — but unlike the infrastructure case above,
each trustee needs to actually *memorize* their codeword rather than
store a file; nobody wants it written on a sticky note. Passing the
bundled EFF long wordlist (`wordlists/eff_large_wordlist.txt` — see
below) with `--dictionary wordlists/eff_large_wordlist.txt
--word-length 8 --word-count 5` builds each codeword out of real,
pronounceable words instead of synthetic strings — the classic
diceware approach, much easier to commit to memory and recall
correctly than an equivalent-strength random string. Since
`load_dictionary()` only pulls words of exactly `--word-length`
characters, pick a length with good coverage in the list (8 characters
has the most candidates, ~1,780, of any length in this wordlist) so
the usable pool — and therefore entropy — stays large; a real
wordlist carries fewer bits per word than the synthetic generator,
which is exactly why word count matters more here — see "Entropy of
the codewords" below.

These two are just illustrations — see [Other potential use
cases](#other-potential-use-cases) below for a broader list spanning
government and business scenarios.

## Files
- `vault_create.py` — CLI Program 1: archive → encrypt → split into trustee codewords → single `.krypt` file
- `vault_recover.py` — CLI Program 2: recover DEK from D codewords → decrypt → extract
- `vault_gui.py` — GUI (Tkinter): same two operations as tabs in a windowed app, with form fields instead of flags
- `vault_core.py` — shared library: the actual encrypt/split and match/reconstruct/decrypt logic; both CLIs and the GUI call this, so there's exactly one implementation of the crypto behind three frontends
- `gf256_sss.py` — shared library: byte-wise Shamir's Secret Sharing over GF(256)
- `wordgen.py` — shared library: codeword generation (synthetic or dictionary-based)
- `kdf.py` — shared library: key derivation (PBKDF2 or Argon2id), self-describing via metadata
- `krypt_container.py` — shared library: the single-file `.krypt` container format
- `wordlists/eff_large_wordlist.txt` — the EFF long wordlist (7,776
  words, one per line), for `--dictionary`-based diceware-style
  codewords; see "Example: diceware-style memorable codewords" above.
  Published by the Electronic Frontier Foundation
  (<https://www.eff.org/dice>) under CC BY 3.0 US; reformatted here
  from EFF's original tab-separated `<dice-roll>\t<word>` file to one
  word per line, since that's the format `wordgen.load_dictionary()`
  expects. A handful of entries with punctuation (`drop-down`,
  `felt-tip`, `t-shirt`, `yo-yo`) get silently excluded by
  `load_dictionary()`'s `isalpha()` filter — expected, negligible.
- `build_appimage.sh` — builds standalone Linux binaries + `.AppImage` packages (CLI and GUI)
- `build_windows.bat` — builds standalone Windows `.exe` files (run on Windows; see below)
- `.github/workflows/build.yml` — GitHub Actions workflow that builds Windows + Linux executables in CI, and publishes a GitHub Release with all of them attached when a `v*` tag is pushed

## Requirements (running from source)
```
pip install cryptography
pip install argon2-cffi   # optional, but strongly recommended (see below)
```
The GUI additionally needs Tkinter, which ships with most Python
installs; on some minimal Linux distros it's a separate package
(`sudo apt install python3-tk` on Debian/Ubuntu). Windows and macOS
python.org installers include it by default.

Python 3.9+ (3.12 recommended; `filter="data"` extraction requires 3.12,
or 3.11.4+ — on older versions drop that argument from `tar.extractall(...)`
in vault_recover.py / vault_core.py).

**All three frontends check for `cryptography` before doing anything else**
and, if it's missing, show the exact `pip install` command to run instead
of a raw traceback — a dialog box in the GUI's case, since it may not even
have a terminal to print to.

`argon2-cffi` is optional. If it's installed, vault creation prefers
Argon2id; if it isn't:
- **CLI**: prints a warning and prompts `Proceed with the PBKDF2 fallback
  anyway? [y/N]` (or aborts safely if non-interactive and `--yes` wasn't
  passed).
- **GUI**: shows the same warning as a Yes/No dialog before proceeding.

Recovery has no fallback either way — the KDF choice was fixed when the
vault was created, so both frontends just show a clear "install
argon2-cffi" message if a vault needs it and it's missing.

## Quick start (CLI)

Create a vault from a file or directory, 5 trustees, 3 needed to recover,
8-character codewords, 2 words per trustee for entropy margin:
```
python3 vault_create.py --input ./my_directory \
    --trustees 5 --threshold 3 \
    --word-length 8 --word-count 2 \
    --outdir vault_out
```
Outputs into `vault_out/`:
- `<random16>.krypt` — **single file** containing both the metadata
  (everything needed to recover, except the codewords) and the encrypted
  archive. This is the one file you back up or share.
- `trustee_words/trustee_1.txt` ... `trustee_5.txt` — one codeword each

Distribute each `trustee_N.txt` to one trustee out-of-band, then delete
them from this machine. The `.krypt` file can be stored, emailed, or
uploaded anywhere — it leaks no information about which codeword belongs
to which share (see "Indexing without a mapping table" below).

Recover (interactive prompt for 3 codewords):
```
python3 vault_recover.py vault_out/xxxxxxxxxxxxxxxx.krypt --outdir recovered
```
Or non-interactively:
```
python3 vault_recover.py vault_out/xxxxxxxxxxxxxxxx.krypt --outdir recovered \
    --word "word-one" --word "word-two" --word "word-three"
```
`--vault-dir vault_out` also works and will find the `.krypt` file inside
automatically (and still understands older split-file vaults — see below).

### Choosing / tuning the KDF

```
--kdf {argon2id,pbkdf2}          # default: argon2id if available, else prompts to fall back
--yes / -y                       # auto-accept the PBKDF2 fallback warning, no prompt
--pbkdf2-iterations N            # default 400000
--argon2-time-cost N             # default 3
--argon2-memory-cost-kib N       # default 65536 (64 MiB)
--argon2-parallelism N           # default 4
```

### Stronger codewords (`--strong-words`)

```
python3 vault_create.py --input ./my_directory \
    --trustees 5 --threshold 3 \
    --word-length 8 --word-count 2 --strong-words \
    --outdir vault_out
```
Opt-in, off by default. Randomizes the case of each generated letter
and appends a 3-digit suffix to every word, e.g. `bAfOgE472` instead
of `bafoge`. Same length/word-count settings, meaningfully more
entropy:
- Randomized case doubles the alphabet at every letter position — +1
  bit/char for free, no extra length.
- The digit suffix adds ~3.32 bits/char, which is denser than the
  vowel slots in the plain alternating-consonant-vowel scheme (the
  actual entropy bottleneck — see "Entropy of the codewords" below).

Only turn this on if codewords will be typed or copy-pasted rather
than read aloud or handwritten — case is the first thing lost in
dictation or sloppy transcription. It's purely a generation-time
choice (recovery just tries whatever string a trustee enters against
each share's KDF+AES-GCM check), so it doesn't touch the `.krypt`
format and can't break compatibility with codewords generated before
this flag existed. Both `vault_create.py` and the GUI log/record an
estimated combinatorial-entropy figure (in bits) for the codewords
they generate, with or without `--strong-words`.

## GUI

```
python3 vault_gui.py
```
Two tabs:
- **Create Vault** — pick a file/folder, fill in trustee count,
  threshold, codeword length/count, a "Strong words" checkbox (see
  `--strong-words` above), output folder, and a KDF option (Auto /
  Argon2id / PBKDF2), then click Create. Progress and log output
  stream into the window, including an estimated codeword-entropy
  figure; a completion dialog shows where the `.krypt` file and
  trustee codeword files landed.
- **Recover Vault** — pick the `.krypt` file and click "Load Vault
  Info" to see how many codewords are needed; that many password-style
  entry fields appear automatically. Fill in the codewords, pick an
  output folder, click Recover.

The GUI runs the actual crypto work on a background thread so the
window stays responsive, and streams log lines back to the main thread
safely via a queue — long Argon2id derivations or large archives won't
freeze the UI.

## Portable builds (no Python/pip needed on the target machine)

### Linux: `build_appimage.sh`

Builds two `.AppImage` files — self-contained Linux executables that
bundle a Python interpreter plus `cryptography` and `argon2-cffi`, so
end users need nothing installed beyond the AppImage file itself. Both
were built and tested (including the GUI, screenshot-verified) in an
environment with no Python, no Tk, no pip packages, and no
`argon2-cffi` present at all.

```
./build_appimage.sh
```
Output:
- `dist/VaultTool-x86_64.AppImage` — CLI, `create`/`recover` subcommands
  (`encrypt`/`decrypt` also work as aliases)
- `dist/VaultToolGUI-x86_64.AppImage` — GUI, double-click or run it

```
./VaultTool-x86_64.AppImage create --input ./my_directory --trustees 5 --threshold 3 --word-length 8 --word-count 2
./VaultTool-x86_64.AppImage recover VAULT.krypt
./VaultToolGUI-x86_64.AppImage
```
If FUSE isn't available on the target machine (common in containers/CI),
add `--appimage-extract-and-run` right after the AppImage path — tested
and works identically for both.

How it's built: **PyInstaller** (`--onefile`, `--windowed` for the GUI)
compiles each script plus its full dependency closure — including
`cryptography`'s OpenSSL bindings, `argon2-cffi`'s C extension, and for
the GUI, Tkinter/Tcl/Tk — into one self-extracting ELF binary per
program. Those binaries get wrapped in a minimal AppDir (`AppRun`
dispatcher + `.desktop` file + icon) and packaged with `appimagetool`
into the familiar single-file AppImage format: `chmod +x` and run, no
installation, no `sudo`.

### Windows: `build_windows.bat`

**Must be run on an actual Windows machine** — PyInstaller does not
cross-compile, so there is no way to produce a working Windows `.exe`
from Linux or macOS. Copy all the `.py` files plus `build_windows.bat`
onto a Windows machine with Python 3.9+ installed (python.org installer,
with "Add to PATH" checked), then run:
```
build_windows.bat
```
Output in `dist\`:
- `VaultTool-GUI.exe` — double-click, opens the windowed GUI
- `vault-create.exe`, `vault-recover.exe` — CLI equivalents

These run standalone on any Windows 10/11 x64 machine: no Python, no
pip packages, nothing else needs installing there. (I built and tested
the Linux binaries and AppImages directly in this environment; the
Windows build script uses the identical PyInstaller invocations, but I
have no Windows machine here to run it on, so it's untested by me —
flag anything odd if it comes up.)

### Don't have a Windows machine? Use GitHub Actions (`.github/workflows/build.yml`)

This workflow is already wired up in this repo and builds both Windows
and Linux executables on GitHub's own runners — a real Windows `.exe`,
built on real Windows, without you needing to own one. Every push to
`main` builds fresh binaries and uploads them as downloadable,
workflow-run artifacts (`VaultTool-windows-x64`, `VaultTool-linux-x64`)
on that run's **Actions** summary page — but those expire and aren't
versioned.

**To publish a proper Release** (all four binaries — both `.exe`s and
both AppImages — attached to a permanent, versioned download page),
push a tag matching `v*`:
```
git tag v1.0.0
git push --tags
```
That triggers the same Windows/Linux builds, then a `release` job
downloads their outputs and runs `gh release create` to publish them
as a GitHub Release named after the tag, with auto-generated release
notes from the commits since the previous tag. Ordinary pushes to
`main` (no new tag) never create a Release — only tag pushes do.

To use this workflow in a *different* repo from scratch, put the
`.py` files, `build_appimage.sh`, and this file at
`.github/workflows/build.yml`, then push.

## Legacy split-file vaults

Vaults created by an earlier version of these scripts (a separate
`metadata.json` + `<name>.crypt` in a directory) still recover fine:
```
python3 vault_recover.py --vault-dir old_vault_dir --outdir recovered
```
or explicitly:
```
python3 vault_recover.py --crypt-file old.crypt --metadata metadata.json --outdir recovered
```
`vault_create.py` only ever produces the new single-file `.krypt` format
going forward.

## How the design works

1. **Archive**: `tar` bundles the file/directory into one blob so any
   input shape works uniformly.
2. **DEK + AES-256-GCM**: a random 32-byte key encrypts the archive
   once. GCM gives you both confidentiality and tamper detection.
3. **Shamir split (GF(256), byte-wise)**: same construction as the
   classic `ssss` tool — each byte of the DEK gets an independent
   random polynomial of degree `D-1`; each share evaluates all 32
   polynomials at the same x-coordinate. Any `D` shares reconstruct
   the DEK via Lagrange interpolation; any `D-1` reveal *nothing*
   (information-theoretic security, not just computational).
4. **Per-share protection**: each share is itself AES-256-GCM
   encrypted under a key derived from a random codeword, using
   either Argon2id (preferred, memory-hard) or PBKDF2-HMAC-SHA256
   (zero extra dependency fallback) — see `kdf.py`.
5. **Single-file container**: metadata and ciphertext are bundled into
   one `.krypt` file — an 8-byte magic header, a length-prefixed JSON
   metadata block, then the raw ciphertext bytes (not base64-wrapped, so
   there's no ~33% size penalty). See `krypt_container.py`. There's
   nothing to accidentally separate or lose track of anymore.
6. **Indexing without a mapping table**: the metadata stores each share
   as an opaque `{salt, nonce, ciphertext}` triple — nothing ties a
   record to a trustee or a word. On recovery, each entered codeword is
   tried against every not-yet-matched record; GCM's authentication tag
   means only the correct pairing decrypts successfully, everything else
   fails fast. With T in the tens this is instant, and it means the
   `.krypt` file by itself reveals zero assignment information even if
   someone else gets hold of it.

## Things worth knowing before you rely on this

- **Entropy of the codewords is the real security bottleneck.**
  A single N-character word — from a real dictionary or the built-in
  synthetic generator — is much weaker than the AES-256/Shamir math
  around it. A natural-language dictionary filtered to a fixed length
  is often only hundreds to low-thousands of candidates (~8–11 bits).
  The built-in synthetic generator (alternating consonant/vowel,
  default when you don't pass `--dictionary`) has a much larger space
  per length, but you should still set `--word-count 2` or higher —
  each extra word roughly multiplies the search space, so 2–3 words
  gets you into a realistic security range. Treat `--word-length`
  as "how long/typeable is each word" and `--word-count` as "how much
  entropy do I actually want." `--strong-words` (see above) raises the
  bits-per-character of each word without adding length, if codewords
  will be typed/pasted rather than spoken or handwritten. Note that
  because each share is cracked independently (see "Indexing without
  a mapping table" above), a higher threshold `D` does *not* let you
  get away with weaker codewords — every codeword individually needs
  to carry real entropy, regardless of `T`.
- **Argon2id vs. PBKDF2**: Argon2id's memory-hardness is what raises
  the cost of an attacker running many parallel guesses on GPUs/ASICs
  against a leaked `.krypt` file — PBKDF2 is cheap to parallelize by
  comparison at equivalent wall-clock cost. The defaults (`time_cost=3`,
  `memory_cost=64 MiB`, `parallelism=4`) are a reasonable balance of
  security and usability on typical hardware; raise
  `--argon2-memory-cost-kib` if you want to make large-scale offline
  guessing meaningfully more expensive, at the cost of slower recovery
  and more RAM used per attempt on your own machine too.
- **Threshold security is information-theoretic; codeword security is
  not.** Getting `D-1` shares gives an attacker literally zero bits
  about the DEK regardless of computing power. Getting a codeword
  right is a matter of guessing effort — that's the piece to size
  according to your threat model (word length, word count, and KDF
  cost together).
- **Back up the `.krypt` file durably** — losing it makes the vault
  unrecoverable regardless of how many codewords you have. Since it's
  a single file now, this is simpler than before, but still worth
  saying out loud.
- Uncompressed `tar` is used deliberately (mode `"w"` not `"w:gz"`) so
  ciphertext size doesn't vary with plaintext compressibility any
  more than necessary; switch to `"w:gz"` in `make_archive()` if you
  want compression and don't mind that leak.

## Other potential use cases

Beyond the two worked examples above, threshold-recoverable encryption
generally fits situations where a policy or legal requirement says "no
single party should be able to unilaterally decrypt this," and access
is rare/high-stakes rather than continuous.

**Government**
- **Two-person-rule systems, generalized to N-of-M** — e.g. "any 3 of
  7 officials," which tolerates absence/incapacitation without
  weakening the no-lone-actor requirement of the classic two-key model.
- **Escrowed decryption keys for classified/lawful-intercept archives**,
  split across officials from different branches/agencies so no single
  agency — or a rogue insider within one — can unilaterally decrypt.
- **Continuity-of-government credentials** that must survive the loss
  of some custodians but still require majority agreement to invoke.
- **Election-system key management** — tabulation-system decryption
  keys split among representatives of multiple parties/observers.
- **Diplomatic/intelligence material** where the "no mapping table"
  property matters most: seizing several codewords in one raid still
  reveals nothing about who holds the rest.

**Business**
- **M&A / escrow and dispute-resolution vaults** — deal terms or
  sensitive documents split among board members, outside counsel, and
  an escrow agent, released only by quorum.
- **Cryptocurrency/treasury cold storage** — an offline way to split
  the root key material behind a multisig wallet among founders/board,
  so no single executive can move funds alone.
- **"Break-glass" access to root credentials** — CA keys, database
  master keys, infrastructure override codes — day-to-day access
  requires zero people, emergency access requires several specific
  people to jointly agree, with an audit trail per trustee.
- **Whistleblower/source-protection archives** for journalism or legal
  teams, releasable only if a threshold of editors/lawyers agree.
- **Estate planning / key-person risk** — a founder's critical
  passwords or IP split among heirs, a lawyer, and a business partner.
- **Regulated data with separation-of-duties requirements** (SOX,
  HIPAA "minimum necessary" contexts) — a technical enforcement of an
  existing compliance control rather than just a policy on paper.

**Where this tool fits best:** rare, high-stakes, offline "break
glass" access with a small (tens, not thousands), semi-static trustee
set, where the vault file itself needs to be safely storable/shareable
with zero metadata leakage about who holds what. It's a poor fit for
frequent/live authorization, revoking a single trustee without a full
re-split, or online multi-party protocols — that's the domain of
proper threshold-signature schemes (e.g. FROST) or HSM-backed
multisig, which support key rotation and live quorum that this
static, split-once design doesn't.
