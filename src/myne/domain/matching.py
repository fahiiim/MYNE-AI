import re

from myne.domain.brands import brand_aliases
from myne.domain.models import BagIdentity, MatchQuality
from myne.domain.text import contains_phrase, normalize_text

_MODEL_STOPWORDS = frozenset({"bag", "bags", "handbag", "handbags", "purse", "the", "a", "de"})

# Accessories and look-alikes that share the model name but not the price.
_EXCLUSION_PHRASES: tuple[str, ...] = (
    "dust bag", "dustbag", "strap", "insert", "organizer", "organiser", "shaper", "pillow",
    "charm", "twilly", "box only", "receipt", "rain cover", "keychain", "key holder",
    "wallet", "card holder", "pouch", "replica", "inspired", "dupe", "style", "lookalike",
    "custom painted", "base shaper", "protector", "sticker",
)  # fmt: skip

_DIGITS = re.compile(r"\d+")


class ListingMatcher:
    """Decides whether a marketplace title refers to the identified bag.

    Brand and every model token must match. Missing qualifiers (size, construction,
    special variant) downgrade the match to PARTIAL rather than rejecting it, so the
    price service can fall back when exact-variant listings are scarce.
    """

    def __init__(self, identity: BagIdentity) -> None:
        self._brand_aliases = brand_aliases(identity.brand)
        brand_tokens = {token for alias in self._brand_aliases for token in alias.split()}

        model_text = normalize_text(identity.model)
        self._model_tokens = tuple(
            token
            for token in model_text.split()
            if token not in _MODEL_STOPWORDS and token not in brand_tokens
        )
        self._exclusions = tuple(
            phrase for phrase in _EXCLUSION_PHRASES if not contains_phrase(model_text, phrase)
        )
        self._qualifiers = tuple(
            spellings
            for spellings in (
                _size_variants(identity.size),
                _phrase_variants(identity.construction),
                _phrase_variants(identity.variant),
            )
            if spellings
        )

    def evaluate(self, title: str) -> MatchQuality | None:
        text = normalize_text(title)
        if not any(contains_phrase(text, alias) for alias in self._brand_aliases):
            return None
        if not all(contains_phrase(text, token) for token in self._model_tokens):
            return None
        if any(contains_phrase(text, phrase) for phrase in self._exclusions):
            return None
        for spellings in self._qualifiers:
            if not any(contains_phrase(text, spelling) for spelling in spellings):
                return MatchQuality.PARTIAL
        return MatchQuality.EXACT


def _phrase_variants(value: str | None) -> tuple[str, ...]:
    text = normalize_text(value or "")
    return (text,) if text else ()


def _size_variants(size: str | None) -> tuple[str, ...]:
    if not size:
        return ()
    text = normalize_text(size)
    if digits := _DIGITS.search(text):
        number = digits.group()
        return (number, f"{number}cm")
    return (text,) if text else ()
