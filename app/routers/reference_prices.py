from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.models import ReferencePrice

router = APIRouter()


@router.post("/reference-prices")
def create_reference_price(
    wine_vintage_id: int = Form(...),
    price: float = Form(...),
    currency: str = Form("USD"),
    price_type: str = Form("avg_retail"),
    source: str = Form("wine-searcher"),
    bottle_size_ml: int = Form(750),
    session: Session = Depends(get_session),
):
    ref = ReferencePrice(
        wine_vintage_id=wine_vintage_id,
        price=price,
        currency=currency,
        price_type=price_type,
        source=source,
        bottle_size_ml=bottle_size_ml,
    )
    session.add(ref)
    session.commit()
    return RedirectResponse(url="/wines", status_code=303)
