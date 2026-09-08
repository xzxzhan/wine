from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import Wine, WineVintage, normalize_name

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/wines")
def list_wines(request: Request, session: Session = Depends(get_session)):
    wines = session.exec(select(Wine)).all()
    vintages_by_wine = {
        wine.id: session.exec(
            select(WineVintage).where(WineVintage.wine_id == wine.id)
        ).all()
        for wine in wines
    }

    all_vintages = []
    for wine in wines:
        for vintage in vintages_by_wine[wine.id]:
            year_label = vintage.vintage_year or "NV"
            label = f"{wine.producer} {wine.wine_name} {year_label}"
            all_vintages.append({"id": vintage.id, "label": label})

    return templates.TemplateResponse(
        "wines.html",
        {
            "request": request,
            "wines": wines,
            "vintages_by_wine": vintages_by_wine,
            "all_vintages": all_vintages,
        },
    )


@router.post("/wines")
def create_wine(
    producer: str = Form(...),
    wine_name: str = Form(...),
    region: Optional[str] = Form(None),
    vintage_year: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    norm = normalize_name(producer, wine_name)
    wine = session.exec(select(Wine).where(Wine.normalized_name == norm)).first()
    if wine is None:
        wine = Wine(
            producer=producer,
            wine_name=wine_name,
            region=region or None,
            normalized_name=norm,
        )
        session.add(wine)
        session.commit()
        session.refresh(wine)

    year = int(vintage_year) if vintage_year and vintage_year.strip() else None
    vintage = session.exec(
        select(WineVintage).where(
            WineVintage.wine_id == wine.id,
            WineVintage.vintage_year == year,
        )
    ).first()
    if vintage is None:
        vintage = WineVintage(wine_id=wine.id, vintage_year=year)
        session.add(vintage)
        session.commit()

    return RedirectResponse(url="/wines", status_code=303)
