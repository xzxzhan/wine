import httpx
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.db import engine, init_db
from app.ingest.refresh import refresh_plumedhorse
from app.models import Listing
from app.routers import deals, listings, reference_prices, wines

app = FastAPI(title="Underpriced Wine Finder")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(wines.router)
app.include_router(reference_prices.router)
app.include_router(listings.router)
app.include_router(deals.router)


@app.on_event("startup")
def on_startup():
    init_db()
    with Session(engine) as session:
        has_data = session.exec(select(Listing.id).limit(1)).first() is not None
    if not has_data:
        try:
            refresh_plumedhorse()
        except httpx.HTTPError:
            pass  # first run with no network -- /deals will just be empty until a manual refresh


@app.get("/")
def root():
    return RedirectResponse(url="/deals")
