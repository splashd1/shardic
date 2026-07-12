"""
vault_core_prime.py

"shardic-prime" variant of vault_core.py: same threshold-recoverable
vault, plus one PRIME trustee whose codeword must always be present at
recovery time. The remaining trustees stay a plain interchangeable
k-of-n pool -- see gf256_sss_prime.py for the layered split/reconstruct
construction this is built on.

Deliberately a separate module/CLI/container-format from the base
scheme (container_format "krypt1-prime", not "krypt1", plus a
"scheme": "prime-trustee" metadata tag) rather than a flag on the
original -- so a base-scheme vault can never accidentally be opened
with prime-aware tooling or vice versa, and vault_core.py's plain
uniform scheme stays untouched.

`trustees` (T) and `threshold` (D) here count the prime trustee: T
total participants = 1 prime + (T-1) pool trustees; D codewords
required to recover = the prime's + (D-1) from the pool.

Share records keep the same opaque {salt, nonce, ciphertext} shape as
the base scheme, and are shuffled together the same way -- so which
record belongs to the prime trustee is not visible from the container
structure either, only from decrypting it with the right codeword.
The encrypted payload carries a one-byte type tag (SHARE_TYPE_PRIME /
SHARE_TYPE_POOL) so a codeword's role is only learned once it matches.
"""

import base64
import os
import secrets
import tarfile
import tempfile
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gf256_sss_prime import split_secret_with_prime, reconstruct_secret_with_prime
from wordgen import estimate_word_entropy_bits, load_dictionary, pick_words
import kdf as kdfmod
import krypt_container
import vault_core as base

DEK_LEN = base.DEK_LEN
SALT_LEN = base.SALT_LEN
NONCE_LEN = base.NONCE_LEN

VaultError = base.VaultError

SHARE_TYPE_PRIME = 0
SHARE_TYPE_POOL = 1


def _noop_log(msg: str) -> None:
    pass


def create_vault_prime(
    input_path: str,
    trustees: int,
    threshold: int,
    word_length: int,
    word_count: int = 1,
    dictionary_path: str | None = None,
    outdir: str | None = None,
    kdf_method: str = "pbkdf2",
    kdf_params: dict | None = None,
    randomize_case: bool = False,
    digit_suffix_len: int = 0,
    log=_noop_log,
) -> dict:
    """
    Like vault_core.create_vault, except one of the `trustees` is a
    PRIME trustee whose codeword is required for every recovery,
    alongside any (threshold - 1) of the remaining (trustees - 1) pool
    trustees.

    Returns the same shape as create_vault, plus "prime_trustee_file".
    """
    if threshold < 2:
        raise ValueError(
            "threshold (D) must be >= 2: 1 mandatory prime codeword + "
            ">= 1 from the pool"
        )
    if trustees < 2:
        raise ValueError("trustees (T) must be >= 2: 1 prime trustee + >= 1 pool trustee")
    if threshold > trustees:
        raise ValueError("threshold (D) cannot exceed trustees (T)")
    if not (2 <= trustees <= 255):
        raise ValueError("trustees (T) must be between 2 and 255")
    if word_length < 3:
        raise ValueError("word length should be at least 3")
    if not os.path.exists(input_path):
        raise ValueError(f"input path not found: {input_path}")

    pool_size = trustees - 1
    pool_threshold = threshold - 1

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

    entropy_bits = estimate_word_entropy_bits(
        word_length,
        word_count,
        dictionary_size=len(dictionary_words) if dictionary_words else None,
        randomize_case=randomize_case,
        digit_suffix_len=digit_suffix_len,
    )
    style_bits = []
    if randomize_case:
        style_bits.append("mixed case")
    if digit_suffix_len:
        style_bits.append(f"+{digit_suffix_len} digit suffix")
    style = f" ({', '.join(style_bits)})" if style_bits else ""
    log(
        f"Estimated codeword strength: ~{entropy_bits:.0f} bits combinatorial per "
        f"trustee{style} (before any KDF stretching), same for the prime "
        f"trustee and the pool -- recovery cracks each codeword independently."
    )

    with tempfile.TemporaryDirectory() as tmp:
        tar_path = os.path.join(tmp, "archive.tar")
        log(f"Archiving '{input_path}' ...")
        base.make_archive(input_path, tar_path)
        with open(tar_path, "rb") as f:
            plaintext = f.read()

    dek = secrets.token_bytes(DEK_LEN)
    archive_nonce = secrets.token_bytes(NONCE_LEN)
    ciphertext = AESGCM(dek).encrypt(archive_nonce, plaintext, associated_data=None)

    mask, pool_shares = split_secret_with_prime(dek, pool_threshold=pool_threshold, pool_size=pool_size)
    log(
        f"Split DEK into 1 prime share + {pool_size} pool shares, pool "
        f"threshold {pool_threshold} (total required to recover: {threshold})"
    )

    def _seal(codeword: str, payload: bytes) -> dict:
        salt = secrets.token_bytes(SALT_LEN)
        share_key = kdfmod.derive_key(kdf_method, kdf_params, codeword, salt)
        share_nonce = secrets.token_bytes(NONCE_LEN)
        share_ct = AESGCM(share_key).encrypt(share_nonce, payload, associated_data=None)
        return {
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(share_nonce).decode(),
            "ciphertext": base64.b64encode(share_ct).decode(),
        }

    share_records = []
    trustee_files = []

    prime_codeword = pick_words(
        word_length, word_count, dictionary_words,
        randomize_case=randomize_case, digit_suffix_len=digit_suffix_len,
    )
    share_records.append(_seal(prime_codeword, bytes([SHARE_TYPE_PRIME]) + mask))
    prime_file = os.path.join(words_dir, "trustee_prime.txt")
    with open(prime_file, "w") as f:
        f.write(prime_codeword + "\n")
    trustee_files.append(prime_file)

    for i, (x, y) in enumerate(pool_shares, start=1):
        codeword = pick_words(
            word_length, word_count, dictionary_words,
            randomize_case=randomize_case, digit_suffix_len=digit_suffix_len,
        )
        share_records.append(_seal(codeword, bytes([SHARE_TYPE_POOL, x]) + y))
        trustee_file = os.path.join(words_dir, f"trustee_{i}.txt")
        with open(trustee_file, "w") as f:
            f.write(codeword + "\n")
        trustee_files.append(trustee_file)

    secrets.SystemRandom().shuffle(share_records)

    metadata = {
        "version": 1,
        "container_format": "krypt1-prime",
        "scheme": "prime-trustee",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive_nonce": base64.b64encode(archive_nonce).decode(),
        "trustees_total": trustees,
        "threshold": threshold,
        "pool_size": pool_size,
        "pool_threshold": pool_threshold,
        "word_length": word_length,
        "word_count": word_count,
        "randomize_case": randomize_case,
        "digit_suffix_len": digit_suffix_len,
        "kdf": kdf_method,
        "kdf_params": kdf_params,
        "salt_len": SALT_LEN,
        "nonce_len": NONCE_LEN,
        "shares": share_records,
    }
    krypt_filename = base.random_filename(16) + ".krypt"
    krypt_path = os.path.join(outdir, krypt_filename)
    krypt_container.write_krypt(krypt_path, metadata, ciphertext)
    log(f"Wrote vault container: {krypt_path} ({os.path.getsize(krypt_path)} bytes)")

    return {
        "krypt_path": krypt_path,
        "words_dir": words_dir,
        "trustee_files": trustee_files,
        "prime_trustee_file": prime_file,
        "outdir": os.path.abspath(outdir),
        "estimated_word_entropy_bits": entropy_bits,
    }


def peek_metadata(krypt_path: str) -> dict:
    """Read just the metadata of a shardic-prime .krypt file, without
    attempting any decryption. Raises VaultError if it isn't one."""
    metadata, _ = krypt_container.read_krypt(krypt_path)
    if metadata.get("scheme") != "prime-trustee":
        raise VaultError(
            f"'{krypt_path}' is not a shardic-prime vault "
            f"(scheme={metadata.get('scheme')!r}). Use vault_recover.py "
            "for plain krypt1 vaults."
        )
    return metadata


def resolve_kdf(metadata: dict) -> tuple[str, dict]:
    return base.resolve_kdf(metadata)


def try_match_word_prime(codeword: str, share_records, kdf_method, kdf_params, used_indices):
    """Like vault_core.try_match_word, but decodes the type-tagged
    payload used by the prime-trustee scheme.

    Returns (record_index, kind, value) where kind is "prime" and
    value is the mask bytes, or kind is "pool" and value is
    (x, y_bytes). Returns None if no untried record matches.
    """
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

        share_type = payload[0]
        if share_type == SHARE_TYPE_PRIME:
            return idx, "prime", payload[1:]
        if share_type == SHARE_TYPE_POOL:
            return idx, "pool", (payload[1], payload[2:])
        continue
    return None


def match_codewords_prime(codewords: list[str], metadata: dict):
    """
    Try each codeword in `codewords` against the vault's share records.

    Returns (mask, pool_shares, unmatched_positions):
      mask is the prime trustee's mask bytes, or None if not found.
      pool_shares is a list of (x, y_bytes) from matched pool trustees.
      unmatched_positions are indices into `codewords` that matched nothing.
    """
    kdf_method, kdf_params = resolve_kdf(metadata)
    share_records = metadata["shares"]

    mask = None
    pool_shares = []
    used_indices: set[int] = set()
    unmatched_positions = []

    for pos, word in enumerate(codewords):
        word = word.strip()
        if not word:
            continue
        match = try_match_word_prime(word, share_records, kdf_method, kdf_params, used_indices)
        if match is None:
            unmatched_positions.append(pos)
            continue
        idx, kind, value = match
        used_indices.add(idx)
        if kind == "prime":
            mask = value
        else:
            pool_shares.append(value)

    return mask, pool_shares, unmatched_positions


def reconstruct_and_decrypt_prime(
    metadata: dict,
    ciphertext: bytes,
    mask,
    pool_shares: list,
    outdir: str | None = None,
    log=_noop_log,
) -> dict:
    """
    Given the prime trustee's mask and >= pool_threshold recovered
    pool (x, y) shares, reconstructs the DEK, decrypts the archive,
    and extracts it to `outdir`.

    Returns: {"outdir": str}
    """
    pool_threshold = metadata["pool_threshold"]
    if mask is None:
        raise VaultError(
            "The prime trustee's codeword was not among those entered -- "
            "this vault cannot be recovered without it, no matter how "
            "many pool codewords are supplied."
        )
    if len(pool_shares) < pool_threshold:
        raise VaultError(
            f"Only {len(pool_shares)} of the required {pool_threshold} pool "
            "codewords matched a share (plus the prime trustee's)."
        )

    log("Reconstructing DEK from the prime mask and recovered pool shares ...")
    dek = reconstruct_secret_with_prime(mask, pool_shares)
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
