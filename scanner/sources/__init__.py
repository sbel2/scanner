from .devpost import collect_devpost
from .ical import collect_ical, collect_luma
from .tavily import collect_tavily

__all__ = [
    "collect_devpost",
    "collect_ical",
    "collect_luma",
    "collect_tavily",
    "collect_all",
]


def collect_all() -> list:
    items = []
    for fn in (collect_devpost, collect_luma, collect_ical, collect_tavily):
        try:
            items.extend(fn())
        except Exception as e:
            print(f"[source] {fn.__name__} failed: {e}")
    return items
