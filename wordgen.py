"""
wordgen.py

Generates the human-typeable codeword(s) used to protect each Shamir
share. Two modes:

  * dictionary mode: if --dictionary is supplied, words of exactly
    length N are pulled from that file (one word per line).
  * synthetic mode (default): pronounceable random words of exact
    length N are generated from a consonant/vowel pattern. This is
    used automatically when no dictionary is given, and generally
    provides *far* more candidates per length than a natural-language
    dictionary does -- a real dictionary filtered to, say, 6-letter
    words might only have a few hundred entries (~8-9 bits of
    entropy), whereas the synthetic generator below has on the order
    of 26 * 5 * 21 * 5 * 21 ... combinations depending on length.

Security note: whichever mode you use, a single short word is weak
entropy on its own. Use --word-count > 1 to concatenate multiple
words per share if you want a real security margin -- see the
--word-count flag on vault_create.py.
"""

import secrets

_VOWELS = "aeiou"
_CONSONANTS = "bcdfghjklmnpqrstvwxyz"


def load_dictionary(path: str, length: int):
    words = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            w = line.strip().lower()
            if len(w) == length and w.isalpha():
                words.append(w)
    if not words:
        raise ValueError(
            f"No words of length {length} found in dictionary file: {path}"
        )
    return words


def synthetic_word(length: int) -> str:
    """Generate one pronounceable random word of exactly `length` chars,
    alternating consonant/vowel starting with a consonant."""
    chars = []
    for i in range(length):
        pool = _CONSONANTS if i % 2 == 0 else _VOWELS
        chars.append(pool[secrets.randbelow(len(pool))])
    return "".join(chars)


def pick_words(length: int, count: int, dictionary_words=None) -> str:
    """
    Return a codeword string made of `count` words of `length`
    characters each, joined by hyphens. If dictionary_words is given,
    words are drawn from it (without replacement within the phrase
    when possible); otherwise synthetic pronounceable words are used.
    """
    parts = []
    if dictionary_words:
        pool = list(dictionary_words)
        for _ in range(count):
            if not pool:
                pool = list(dictionary_words)  # allow reuse if we run out
            idx = secrets.randbelow(len(pool))
            parts.append(pool.pop(idx))
    else:
        for _ in range(count):
            parts.append(synthetic_word(length))
    return "-".join(parts)
