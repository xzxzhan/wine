from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.models import Listing

router = APIRouter()


@router.post("/listings")
def create_listing(
    wine_vintage_id: int = Form(...),
    source: str = Form(...),
    source_type: str = Form(...),  # "auction" | "restaurant"
    price: float = Form(...),
    currency: str = Form("USD"),
    raw_text: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    listing = Listing(
        wine_vintage_id=wine_vintage_id,
        source=source,
        source_type=source_type,
        price=price,
        currency=currency,
        raw_text=raw_text or None,
    )
    session.add(listing)
    session.commit()
    return RedirectResponse(url="/deals", status_code=303)
