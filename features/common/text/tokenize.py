"""Language-aware tokenization for indexing, clustering, and deduplication.

Folio Board tokenized with ``[A-Za-z0-9가-힣]{2,}`` in four places. That works for
Korean and English and fails two different ways elsewhere, measured on 20 market
headlines per language (Task 0.4):

- **Japanese produces no tokens at all.** 15 of 20 headlines yielded zero, because
  kana and kanji are outside the class. Empty token sets then collapse together,
  so unrelated Japanese items were merging as duplicates — 20 headlines reduced
  to 6 distinct keys.
- **European produces wrong tokens.** 84–100% of non-ASCII words were split or
  truncated at the accent: ``erhält`` → ``['erh', 'lt']``, ``Telefónica`` →
  ``['Telef', 'nica']``, ``troisième`` → ``['troisi', 'me']``.

So the fix differs by script: Europe needs accent folding, Japan needs the CJK
ranges admitted. Korean and English output must not move at all — they are the
existing corpus and the ranking behaviour users already have.
"""
from __future__ import annotations

import re
import unicodedata

# Latin letters, digits and Hangul syllables form one class; kana and Han form a
# second. They are kept apart on purpose. Merging them would join a Hangul run to
# an adjacent Han character — Korean copy abbreviates with them, so `엔비디아向`
# would become a single token and stop matching a search for `엔비디아`, changing
# results on the existing Korean corpus.
_LATIN_CLASS = r"A-Za-z0-9가-힣"
_CJK_CLASS = (
    "぀-ゟ"      # Hiragana
    "゠-ヿ"      # Katakana
    "ㇰ-ㇿ"      # Katakana phonetic extensions
    "一-鿿"      # CJK unified ideographs
    "㐀-䶿"      # CJK extension A
    "豈-﫿"      # CJK compatibility ideographs
    "ｦ-ﾟ"      # Halfwidth katakana
)

TOKEN_RE = re.compile(rf"[{_LATIN_CLASS}]{{2,}}|[{_CJK_CLASS}]{{2,}}")
WORD_RE = re.compile(rf"[{_LATIN_CLASS}]+|[{_CJK_CLASS}]+")

_CJK_RE = re.compile(rf"[{_CJK_CLASS}]")

# Latin letters that carry no combining mark to strip, so NFD leaves them intact
# and they would split a word in half. German ss-ligature is the one that matters
# most for the target countries (Grossauftrag, Strasse); the rest are cheap.
_LATIN_EXPANSIONS = {
    "ß": "ss", "ẞ": "SS",
    "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "TH",
    "ð": "d", "Ð": "D",
}


def has_cjk(text: str) -> bool:
    """Whether the text contains kana or Han characters.

    Hangul is deliberately excluded: Korean is whitespace-delimited and already
    tokenizes correctly, so it must not be routed down the CJK paths.
    """
    return bool(_CJK_RE.search(str(text or "")))


def _is_latin(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def fold_accents(text: str) -> str:
    """Strip combining marks from Latin letters only, then recompose.

    ``Telefónica`` folds to ``Telefonica`` and stays one token instead of
    breaking into ``Telef`` and ``nica``.

    Folding must not be applied blindly. Decomposing everything and dropping all
    marks destroys the other two scripts this codebase handles: Hangul syllables
    decompose into Jamo that fall outside the token class (``삼성전자`` vanishes),
    and Japanese dakuten are separate combining marks, so ``で`` would silently
    become ``て`` — a different character, not an accent. Marks are therefore
    dropped only when they sit on a Latin base, and the result is recomposed so
    Hangul and kana return to their original form.
    """
    result: list[str] = []
    for ch in unicodedata.normalize("NFD", str(text or "")):
        if unicodedata.category(ch) == "Mn" and result and _is_latin(result[-1]):
            continue
        result.append(_LATIN_EXPANSIONS.get(ch, ch))
    return unicodedata.normalize("NFC", "".join(result))


def tokens(text: str, *, min_length: int = 2) -> list[str]:
    """Tokenize for indexing and matching, folding accents first."""
    folded = fold_accents(text)
    if min_length <= 1:
        return WORD_RE.findall(folded)
    return TOKEN_RE.findall(folded)


def token_set(text: str) -> set[str]:
    """Lowercased distinct tokens, for overlap scoring and clustering."""
    return {token.lower() for token in tokens(text)}


def word_count(text: str) -> int:
    """Count word-like runs. Used for length gates on document bodies."""
    return len(WORD_RE.findall(fold_accents(text)))
