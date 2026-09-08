from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.ingest.refresh import refresh_plumedhorse
from app.models import Listing, ReferencePrice, WineVintage
from app.scoring import below_market_pct, best_reference_price

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _latest_listing_per_vintage(session: Session) -> list[Listing]:
    """Most recent listing for each wine_vintage (a re-ingested wine gets a
    fresh Listing row per day; we only want to show the current price)."""
    all_listings = session.exec(select(Listing)).all()
    latest: dict[int, Listing] = {}
    for listing in all_listings:
        key = listing.wine_vintage_id
        current = latest.get(key)
        if current is None or listing.date_seen > current.date_seen:
            latest[key] = listing
    return list(latest.values())


@router.get("/deals")
def list_deals(request: Request, session: Session = Depends(get_session), error: str = ""):
    below_market, above_market, needs_review = [], [], []

    latest_listings = _latest_listing_per_vintage(session)
    last_refreshed = max((l.date_seen for l in latest_listings), default=None)

    for listing in latest_listings:
        vintage = session.get(WineVintage, listing.wine_vintage_id) if listing.wine_vintage_id else None
        if vintage is None:
            needs_review.append({"listing": listing, "reason": "unmatched"})
            continue

        ref_prices = session.exec(
            select(ReferencePrice).where(ReferencePrice.wine_vintage_id == vintage.id)
        ).all()
        ref = best_reference_price(ref_prices)
        if ref is None:
            needs_review.append(
                {"listing": listing, "vintage": vintage, "reason": "no_reference"}
            )
            continue

        pct = below_market_pct(
            listing_price=listing.price,
            listing_bottle_size_ml=listing.bottle_size_ml,
            reference_price=ref.price,
            reference_bottle_size_ml=ref.bottle_size_ml,
        )
        row = {
            "listing": listing,
            "vintage": vintage,
            "reference": ref,
            "pct_below_market": pct,
        }
        (below_market if pct > 0 else above_market).append(row)

    below_market.sort(key=lambda r: r["pct_below_market"], reverse=True)
    above_market.sort(key=lambda r: r["pct_below_market"], reverse=True)

    return templates.TemplateResponse(
        "deals.html",
        {
            "request": request,
            "below_market": below_market,
            "above_market": above_market,
            "needs_review": needs_review,
            "last_refreshed": last_refreshed,
            "error": error,
        },
    )


@router.post("/refresh")
def refresh():
    try:
        refresh_plumedhorse()
    except httpx.HTTPError as e:
        return RedirectResponse(
            url=f"/deals?error=Could+not+reach+Plumed+Horse+({type(e).__name__})",
            status_code=303,
        )
    return RedirectResponse(url="/deals", status_code=303)
