from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import Listing, ReferencePrice, WineVintage
from app.scoring import best_reference_price, score_listing

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/deals")
def list_deals(request: Request, session: Session = Depends(get_session)):
    listings = session.exec(select(Listing)).all()
    rows = []
    for listing in listings:
        if listing.wine_vintage_id is None:
            rows.append({"listing": listing, "status": "unmatched"})
            continue

        vintage = session.get(WineVintage, listing.wine_vintage_id)
        ref_prices = session.exec(
            select(ReferencePrice).where(
                ReferencePrice.wine_vintage_id == listing.wine_vintage_id
            )
        ).all()
        ref = best_reference_price(ref_prices)
        if ref is None:
            rows.append(
                {"listing": listing, "vintage": vintage, "status": "no_reference"}
            )
            continue

        score = score_listing(
            listing_price=listing.price,
            listing_bottle_size_ml=vintage.bottle_size_ml,
            reference_price=ref.price,
            reference_bottle_size_ml=vintage.bottle_size_ml,
            source_type=listing.source_type,
        )
        rows.append(
            {
                "listing": listing,
                "vintage": vintage,
                "reference": ref,
                "score": score,
                "status": "scored",
            }
        )

    rows.sort(
        key=lambda r: r["score"].discount_pct if r["status"] == "scored" else -999,
        reverse=True,
    )

    return templates.TemplateResponse(
        "deals.html", {"request": request, "rows": rows}
    )
