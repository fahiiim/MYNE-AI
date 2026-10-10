from urllib.parse import urlsplit

from myne.domain.models import Condition, MarketSegment
from myne.domain.text import contains_phrase, normalize_text

# Order matters: "like new" must resolve to EXCELLENT before "new" is considered.
_CONDITION_RULES: tuple[tuple[Condition, tuple[str, ...]], ...] = (
    (Condition.EXCELLENT, ("excellent", "like new", "very good", "mint", "pristine")),
    (Condition.FAIR, ("fair", "worn", "heavily used", "damaged", "for parts")),
    (Condition.GOOD, ("good", "gently used", "used", "pre owned", "preowned", "pre loved")),
    (Condition.NEW, ("brand new", "new with tags", "new without tags", "nwt", "unworn", "new")),
)

RESALE_HOSTS = frozenset(
    {
        "fashionphile.com", "therealreal.com", "vestiairecollective.com", "rebag.com",
        "1stdibs.com", "ebay.com", "poshmark.com", "yoogiscloset.com", "theluxurycloset.com",
        "madisonavenuecouture.com", "priveporter.com", "luxurypromise.com",
        "bagista.co.uk", "cosette.com.au", "reebonz.com", "brandoff.com", "luxedh.com",
        "designervault.com", "lxrandco.com", "whatgoesaroundnyc.com", "sothebys.com",
        "christies.com",
    }
)  # fmt: skip

RETAIL_HOSTS = frozenset(
    {
        "hermes.com", "louisvuitton.com", "chanel.com", "dior.com", "gucci.com", "prada.com",
        "ysl.com", "celine.com", "loewe.com", "fendi.com", "bottegaveneta.com",
        "balenciaga.com", "givenchy.com", "valentino.com", "miumiu.com", "burberry.com",
        "chloe.com", "coach.com", "michaelkors.com", "katespade.com", "toryburch.com",
        "net-a-porter.com", "mytheresa.com", "farfetch.com", "ssense.com",
        "saksfifthavenue.com", "neimanmarcus.com", "bergdorfgoodman.com", "nordstrom.com",
        "bloomingdales.com", "harrods.com", "selfridges.com", "luisaviaroma.com", "24s.com",
        "modaoperandi.com",
    }
)  # fmt: skip

_RESALE_SELLER_STEMS = frozenset(host.split(".")[0] for host in RESALE_HOSTS)


def normalize_condition(raw: str | None) -> Condition:
    if not raw:
        return Condition.UNKNOWN
    text = normalize_text(raw)
    for condition, phrases in _CONDITION_RULES:
        if any(contains_phrase(text, phrase) for phrase in phrases):
            return condition
    return Condition.UNKNOWN


def host_in(url: str | None, hosts: frozenset[str]) -> bool:
    if not url:
        return False
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith(f".{h}") for h in hosts)


def is_resale_venue(*, seller: str | None, url: str | None) -> bool:
    if host_in(url, RESALE_HOSTS):
        return True
    if not seller:
        return False
    compact = normalize_text(seller).replace(" ", "")
    return any(stem in compact for stem in _RESALE_SELLER_STEMS)


def classify_listing(
    *,
    condition_hint: str | None,
    seller: str | None,
    url: str | None,
    segment_hint: MarketSegment | None = None,
) -> tuple[MarketSegment, Condition]:
    condition = normalize_condition(condition_hint)
    if segment_hint is not None:
        segment = segment_hint
    elif is_resale_venue(seller=seller, url=url) or condition not in {
        Condition.NEW,
        Condition.UNKNOWN,
    }:
        segment = MarketSegment.RESALE
    else:
        segment = MarketSegment.RETAIL

    if segment is MarketSegment.RETAIL and condition is Condition.UNKNOWN:
        condition = Condition.NEW
    return segment, condition
