import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    """Whole-word containment on already-normalized text ('lv' must not match 'silver')."""
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_text} "


def dedupe_words(value: str) -> str:
    seen: set[str] = set()
    words: list[str] = []
    for word in value.split():
        key = normalize_text(word)
        if key and key not in seen:
            seen.add(key)
            words.append(word)
    return " ".join(words)
