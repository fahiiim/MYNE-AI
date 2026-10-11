import pytest

from myne.domain.matching import ListingMatcher
from myne.domain.models import BagIdentity, MatchQuality

BIRKIN_30 = BagIdentity(brand="Hermès", model="Birkin", size="30")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("HERMES Birkin 30 Togo Gold GHW", MatchQuality.EXACT),
        ("Hermès Birkin 30cm Etoupe Clemence", MatchQuality.EXACT),
        ("Hermes Birkin 25 Noir Togo", MatchQuality.PARTIAL),
        ("Hermes Birkin 30 dust bag only", None),
        ("Hermes Twilly for Birkin 30", None),
        ("Birkin-inspired 30 tote", None),
        ("Hermes Kelly 28", None),
    ],
)
def test_listing_matcher(title: str, expected: MatchQuality | None) -> None:
    assert ListingMatcher(BIRKIN_30).evaluate(title) is expected


def test_construction_and_variant_are_qualifiers() -> None:
    identity = BagIdentity(
        brand="Hermes", model="Kelly", size="28", construction="Sellier", variant="So Black"
    )
    matcher = ListingMatcher(identity)
    assert matcher.evaluate("Hermes Kelly 28 Sellier So Black Box") is MatchQuality.EXACT
    assert matcher.evaluate("Hermes Kelly 28 Sellier Noir Box") is MatchQuality.PARTIAL


def test_brand_aliases_use_whole_words() -> None:
    matcher = ListingMatcher(BagIdentity(brand="Louis Vuitton", model="Neverfull"))
    assert matcher.evaluate("LV Neverfull MM Monogram") is MatchQuality.EXACT
    assert matcher.evaluate("Silver Neverfull lookalike tote") is None


def test_model_containing_excluded_word_is_not_self_excluded() -> None:
    matcher = ListingMatcher(BagIdentity(brand="Chanel", model="Wallet on Chain"))
    assert matcher.evaluate("Chanel Classic Wallet on Chain Caviar") is MatchQuality.EXACT
