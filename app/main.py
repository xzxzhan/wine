from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
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


@app.get("/")
def root():
    return RedirectResponse(url="/wines")
