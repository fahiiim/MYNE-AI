from myne.domain.text import normalize_text

_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("hermes",),
    ("chanel",),
    ("louis vuitton", "lv"),
    ("dior", "christian dior"),
    ("saint laurent", "yves saint laurent", "ysl"),
    ("bottega veneta", "bottega"),
    ("gucci",),
    ("prada",),
    ("celine",),
    ("loewe",),
    ("fendi",),
    ("balenciaga",),
    ("goyard",),
    ("givenchy",),
    ("valentino", "valentino garavani"),
    ("miu miu",),
    ("burberry",),
    ("chloe",),
    ("the row",),
    ("alaia", "azzedine alaia"),
    ("jacquemus",),
    ("delvaux",),
    ("moynat",),
    ("mulberry",),
    ("longchamp",),
    ("ferragamo", "salvatore ferragamo"),
    ("alexander mcqueen", "mcqueen"),
    ("versace",),
    ("dolce gabbana", "dolce and gabbana"),
    ("coach",),
    ("michael kors",),
    ("kate spade",),
    ("tory burch",),
    ("marc jacobs",),
    ("mcm",),
)

_GROUP_BY_ALIAS: dict[str, tuple[str, ...]] = {
    alias: group for group in _ALIAS_GROUPS for alias in group
}


def brand_aliases(brand: str) -> tuple[str, ...]:
    key = normalize_text(brand)
    return _GROUP_BY_ALIAS.get(key, (key,))
