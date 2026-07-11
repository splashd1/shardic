"""
vault_core.py

The actual encrypt/split and match/reconstruct/decrypt logic, factored
out so both the CLI scripts (vault_create.py, vault_recover.py) and the
GUI (vault_gui.py) call the exact same code paths -- no duplicated
crypto logic between the terminal and windowed versions of this tool.

Functions here raise plain exceptions (ValueError, VaultError) rather
than calling sys.exit, so callers (CLI argparse wrapper, or a Tk
dialog) can present errors however fits their interface.
"""

import base64
import os
import secrets
import string
import tarfile
import tempfile
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gf256_sss import split_secret, reconstruct_secret
from wordgen import load_dictionary, pick_words
import kdf as kdfmod
import krypt_container

DEK_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12


class VaultError(Exception):
    """Raised for recoverable, user-facing problems (bad input, wrong
    codewords, corrupted files, missing optional dependency, etc.)."""


def _noop_log(msg: str) -> None:
    pass


def random_filename(n: int = 16) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def make_archive(input_path: str, dest_tar_path: str) -> None:
    """Tar (uncompressed) the input file or directory into dest_tar_path."""
    with tarfile.open(dest_tar_path, "w") as tar:
        arcname = os.path.basename(os.path.normpath(input_path))
        tar.add(input_path, arcname=arcname)


def resolve_kdf_params(kdf_method: str, overrides: dict | None = None) -> dict:
    """overrides is a dict of just the keys the caller wants to change
    from kdfmod.default_params(kdf_method)."""
    params = kdfmod.default_params(kdf_method)
    if overrides:
        params.update({k: v for k, v in overrides.items() if v is not None})
    return params


def create_vault(
    input_path: str,
    trustees: int,
    threshold: int,
    word_length: int,
    word_count: int = 1,
    dictionary_path: str | None = None,
    outdir: str | None = None,
    kdf_method: str = "pbkdf2",
    kdf_params: dict | None = None,
    log=_noop_log,
) -> dict:
    """
    Archives `input_path`, encrypts it, splits the DEK into `trustees`
    Shamir shares (threshold `threshold`), protects each share with a
    codeword, and writes a single .krypt container plus one codeword
    file per trustee.

    Caller is responsible for resolving kdf_method/kdf_params ahead of
    time (including any "argon2 unavailable, fall back?" confirmation)
    -- this function just uses whatever it's given.

    Returns: {"krypt_path": str, "words_dir": str, "trustee_files": [str, ...], "outdir": str}
    """
    if threshold > trustees:
        raise ValueError("threshold (D) cannot exceed trustees (T)")
    if not (1 <= trustees <= 255):
        raise ValueError("trustees (T) must be between 1 and 255")
    if word_length < 3:
        raise ValueError("word length should be at least 3")
    if not os.path.exists(input_path):
        raise ValueError(f"input path not found: {input_path}")

    if kdf_params is None:
        kdf_params = kdfmod.default_params(kdf_method)

    outdir = outdir or f"vault_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    os.makedirs(outdir, exist_ok=True)
    words_dir = os.path.join(outdir, "trustee_words")
    os.makedirs(words_dir, exist_ok=True)

    dictionary_words = None
    if dictionary_path:
        dictionary_words = load_dictionary(dictionary_path, word_length)
        log(f"Loaded {len(dictionary_words)} candidate words of length {word_length} from {dictionary_path}")
    else:
        log("No dictionary supplied; using synthetic pronounceable words.")

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = os.path.join(tmp, "archive.tar")
        log(f"Archiving '{input_path}' ...")
        make_archive(input_path, tar_path)
        with open(tar_path, "rb") as f:
            plaintext = f.read()

    dek = secrets.token_bytes(DEK_LEN)
    archive_nonce = secrets.token_bytes(NONCE_LEN)
    ciphertext = AESGCM(dek).encrypt(archive_nonce, plaintext, associated_data=None)

    shares = split_secret(dek, threshold=threshold, total_shares=trustees)
    log(f"Split DEK into {trustees} shares, threshold {threshold}")

    share_records = []
    trustee_files = []
    for i, (x, y) in enumerate(shares, start=1):
        codeword = pick_words(word_length, word_count, dictionary_words)
        salt = secrets.token_bytes(SALT_LEN)
        share_key = kdfmod.derive_key(kdf_method, kdf_params, codeword, salt)
        share_nonce = secrets.token_bytes(NONCE_LEN)
        payload = bytes([x]) + y
        share_ct = AESGCM(share_key).encrypt(share_nonce, payload, associated_data=None)

        share_records.append({
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(share_nonce).decode(),
            "ciphertext": base64.b64encode(share_ct).decode(),
        })

        trustee_file = os.path.join(words_dir, f"trustee_{i}.txt")
        with open(trustee_file, "w") as f:
            f.write(codeword + "\n")
        trustee_files.append(trustee_file)

    secrets.SystemRandom().shuffle(share_records)

    metadata = {
        "version": 2,
        "container_format": "krypt1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive_nonce": base64.b64encode(archive_nonce).decode(),
        "trustees_total": trustees,
        "threshold": threshold,
        "word_length": word_length,
        "word_count": word_count,
        "kdf": kdf_method,
        "kdf_params": kdf_params,
        "salt_len": SALT_LEN,
        "nonce_len": NONCE_LEN,
        "shares": share_records,
    }
    krypt_filename = random_filename(16) + ".krypt"
    krypt_path = os.path.join(outdir, krypt_filename)
    krypt_container.write_krypt(krypt_path, metadata, ciphertext)
    log(f"Wrote vault container: {krypt_path} ({os.path.getsize(krypt_path)} bytes)")

    return {
        "krypt_path": krypt_path,
        "words_dir": words_dir,
        "trustee_files": trustee_files,
        "outdir": os.path.abspath(outdir),
    }


def peek_metadata(krypt_path: str) -> dict:
    """Read just the metadata of a .krypt file (threshold, trustee count,
    KDF, etc.) without attempting any decryption."""
    metadata, _ = krypt_container.read_krypt(krypt_path)
    return metadata


def resolve_kdf(metadata: dict) -> tuple[str, dict]:
    """Backward compatible with version-1 metadata (PBKDF2 only, flat fields).
    Raises VaultError if the vault needs Argon2id and it's unavailable."""
    if "kdf_params" in metadata:
        kdf_method = metadata["kdf"]
        kdf_params = metadata["kdf_params"]
    else:
        kdf_method = "pbkdf2"
        kdf_params = {"iterations": metadata["kdf_iterations"]}

    if kdf_method == "argon2id" and not kdfmod.ARGON2_AVAILABLE:
        raise VaultError(
            "This vault's shares are protected with Argon2id, but "
            "'argon2-cffi' isn't installed here. Install it and try "
            "again -- there's no fallback for this, since the KDF "
            "choice was fixed when the vault was created."
        )
    return kdf_method, kdf_params


def try_match_word(codeword: str, share_records, kdf_method, kdf_params, used_indices):
    """Try `codeword` against every not-yet-consumed share record.
    Returns (record_index, x, y) on success, else None."""
    for idx, rec in enumerate(share_records):
        if idx in used_indices:
            continue
        salt = base64.b64decode(rec["salt"])
        nonce = base64.b64decode(rec["nonce"])
        ct = base64.b64decode(rec["ciphertext"])
        key = kdfmod.derive_key(kdf_method, kdf_params, codeword, salt)
        try:
            payload = AESGCM(key).decrypt(nonce, ct, associated_data=None)
        except InvalidTag:
            continue
        return idx, payload[0], payload[1:]
    return None


def match_codewords(codewords: list[str], metadata: dict) -> tuple[list, list[int]]:
    """
    Try each codeword in `codewords` against the vault's share records.
    Returns (recovered_shares, unmatched_positions) where recovered_shares
    is a list of (x, y_bytes) and unmatched_positions are indices into
    the input `codewords` list that didn't match anything (skips blanks).
    """
    kdf_method, kdf_params = resolve_kdf(metadata)
    share_records = metadata["shares"]

    recovered = []
    used_indices: set[int] = set()
    unmatched_positions = []

    for pos, word in enumerate(codewords):
        word = word.strip()
        if not word:
            continue
        match = try_match_word(word, share_records, kdf_method, kdf_params, used_indices)
        if match is None:
            unmatched_positions.append(pos)
            continue
        idx, x, y = match
        used_indices.add(idx)
        recovered.append((x, y))

    return recovered, unmatched_positions


def reconstruct_and_decrypt(
    metadata: dict,
    ciphertext: bytes,
    recovered_shares: list,
    outdir: str | None = None,
    log=_noop_log,
) -> dict:
    """
    Given >= threshold recovered (x, y) shares, reconstructs the DEK,
    decrypts the archive, and extracts it to `outdir`.

    Returns: {"outdir": str}
    """
    threshold = metadata["threshold"]
    if len(recovered_shares) < threshold:
        raise VaultError(
            f"Only {len(recovered_shares)} of the required {threshold} "
            "codewords matched a share."
        )

    log("Reconstructing DEK from recovered shares ...")
    dek = reconstruct_secret(recovered_shares)
    if len(dek) != DEK_LEN:
        raise VaultError("Reconstructed key has unexpected length -- shares may be inconsistent.")

    log("Decrypting archive ...")
    archive_nonce = base64.b64decode(metadata["archive_nonce"])
    try:
        plaintext = AESGCM(dek).decrypt(archive_nonce, ciphertext, associated_data=None)
    except InvalidTag:
        raise VaultError(
            "Archive decryption failed authentication. This means the "
            "recovered DEK is wrong (mismatched/insufficient shares) or "
            "the ciphertext is corrupted/tampered. No output was written."
        )

    outdir = outdir or f"recovered_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    os.makedirs(outdir, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tmp.write(plaintext)
        tmp_path = tmp.name
    try:
        with tarfile.open(tmp_path, "r") as tar:
            tar.extractall(outdir, filter="data")
    finally:
        os.remove(tmp_path)

    log(f"Success. Recovered contents extracted to: {os.path.abspath(outdir)}")
    return {"outdir": os.path.abspath(outdir)}
