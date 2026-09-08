"""The local Wine-Searcher price cache's staleness policy.

ReferencePrice rows *are* the local cache -- each carries a date_captured
("last updated") timestamp. This module decides which wines need a fresh
Wine-Searcher lookup: never looked up before, or looked up more than
STALE_DAYS ago. Nothing else should re-query a wine that's still fresh.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Listing, ReferencePrice, WineVintage

STALE_DAYS = 60


def is_stale_or_missing(
    reference_prices: list[ReferencePrice], today: Optional[date] = None
) -> bool:
    """True if this vintage has never been looked up on Wine-Searcher, or
    its most recent lookup is more than STALE_DAYS old."""
    ws_prices = [rp for rp in reference_prices if rp.source == "wine-searcher"]
    if not ws_prices:
        return True
    today = today or date.today()
    most_recent = max(rp.date_captured for rp in ws_prices)
    return (today - most_recent).days >= STALE_DAYS


def _latest_listing_per_vintage(session: Session) -> dict[int, Listing]:
    listings = session.exec(select(Listing)).all()
    latest: dict[int, Listing] = {}
    for listing in listings:
        vid = listing.wine_vintage_id
        if vid is None:
            continue
        current = latest.get(vid)
        if current is None or listing.date_seen > current.date_seen:
            latest[vid] = listing
    return latest


@dataclass
class WorklistItem:
    vintage_id: int
    external_ref: Optional[str]
    raw_text: str
    price: float


def build_worklist(
    session: Session, limit: Optional[int] = None, min_price: float = 0.0
) -> list[WorklistItem]:
    """Wines needing a Wine-Searcher lookup (missing or stale), by current
    listing price descending -- the priciest, highest-upside wines first."""
    latest_by_vintage = _latest_listing_per_vintage(session)
    all_refs = session.exec(select(ReferencePrice)).all()
    refs_by_vintage: dict[int, list[ReferencePrice]] = {}
    for rp in all_refs:
        refs_by_vintage.setdefault(rp.wine_vintage_id, []).append(rp)

    items = []
    for vintage_id, listing in latest_by_vintage.items():
        if listing.price < min_price:
            continue
        if not is_stale_or_missing(refs_by_vintage.get(vintage_id, [])):
            continue
        vintage = session.get(WineVintage, vintage_id)
        items.append(
            WorklistItem(
                vintage_id=vintage_id,
                external_ref=vintage.external_ref if vintage else None,
                raw_text=listing.raw_text or "",
                price=listing.price,
            )
        )

    items.sort(key=lambda i: -i.price)
    return items[:limit] if limit else items


if __name__ == "__main__":
    import sys

    from app.db import engine

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    with Session(engine) as session:
        for item in build_worklist(session, limit=limit):
            print(f"{item.price:>10.2f}  {item.raw_text}  [{item.external_ref}]")
