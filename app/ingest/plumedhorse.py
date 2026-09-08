"""Pulls Plumed Horse's current wine list from their public WooCommerce
Store API (the same data that powers the product table on
https://plumedhorse.com/wine/) and upserts it as Wine/WineVintage/Listing
rows.

This endpoint is WooCommerce's standard public storefront API (used by the
site's own JS to render the page) -- not a scrape of rendered HTML or a
bypass of any block. Wine-Searcher reference prices are handled separately
(see reference_prices_plumedhorse.csv + load_references.py) since
Wine-Searcher blocks automated fetches and requires a different approach.
"""
import re
from datetime import date
from typing import Optional

import httpx
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Listing, Wine, WineVintage, normalize_name

STORE_API = "https://plumedhorse.com/wp-json/wc/store/v1/products"
WINE_CATEGORY_IDS = "99,100"  # White Bottles, Red Bottles
SOURCE = "restaurant:Plumed Horse"

VINTAGE_RE = re.compile(r"^(NV|N\.V\.|\d{4})\s+")
HALF_BOTTLE_RE = re.compile(r"half\s*bottle", re.IGNORECASE)


def fetch_raw_products() -> list[dict]:
    resp = httpx.get(
        STORE_API,
        params={"category": WINE_CATEGORY_IDS, "per_page": 100},
        timeout=30,
        headers={"User-Agent": "wine-underpriced-finder/0.1 (personal project)"},
    )
    resp.raise_for_status()
    return resp.json()


def _clean_name(raw_name: str) -> str:
    import html

    return html.unescape(raw_name).strip()


def parse_product_name(raw_name: str) -> tuple[Optional[int], str, str]:
    """Best-effort split of a product title into (vintage_year, producer, wine_name).

    This is a light heuristic, not a real parser: producer/wine_name split is
    for display only. Automated re-matching relies on the WooCommerce product
    id (external_ref), not this text, so an imperfect split here doesn't
    break correctness -- see WineVintage.external_ref.
    """
    name = _clean_name(raw_name)

    vintage_year = None
    m = VINTAGE_RE.match(name)
    rest = name
    if m:
        token = m.group(1)
        rest = name[m.end():].strip()
        if token.upper() not in ("NV", "N.V."):
            vintage_year = int(token)

    # Drop a parenthetical like "(half bottle)" from the display name.
    rest_display = re.sub(r"\s*\(half\s*bottle\)\s*", "", rest, flags=re.IGNORECASE).strip()

    before_comma = rest_display.split(",", 1)[0]
    words = before_comma.split()
    if len(words) >= 3:
        producer = " ".join(words[:2])
    elif len(words) == 2:
        producer = words[0]
    else:
        producer = before_comma
    wine_name = rest_display[len(producer):].strip(" ,\"“”") or rest_display

    return vintage_year, producer or "Unknown", wine_name or rest_display


def parse_price_usd(product: dict) -> float:
    prices = product["prices"]
    minor = prices["currency_minor_unit"]
    return int(prices["price"]) / (10 ** minor)


def ingest() -> dict:
    init_db()
    raw_products = fetch_raw_products()

    n_created_wines = n_created_vintages = n_listings = n_updated = 0

    with Session(engine) as session:
        for product in raw_products:
            external_ref = f"plumedhorse:{product['id']}"
            raw_name = product["name"]
            vintage_year, producer, wine_name = parse_product_name(raw_name)
            price = parse_price_usd(product)
            bottle_size_ml = 375 if HALF_BOTTLE_RE.search(raw_name) else 750

            vintage = session.exec(
                select(WineVintage).where(WineVintage.external_ref == external_ref)
            ).first()

            if vintage is None:
                norm = normalize_name(producer, wine_name)
                wine = Wine(
                    producer=producer,
                    wine_name=wine_name,
                    region=None,
                    normalized_name=norm,
                )
                session.add(wine)
                session.commit()
                session.refresh(wine)
                n_created_wines += 1

                vintage = WineVintage(
                    wine_id=wine.id,
                    vintage_year=vintage_year,
                    external_ref=external_ref,
                )
                session.add(vintage)
                session.commit()
                session.refresh(vintage)
                n_created_vintages += 1
            else:
                n_updated += 1

            existing_today = session.exec(
                select(Listing).where(
                    Listing.wine_vintage_id == vintage.id,
                    Listing.source == SOURCE,
                    Listing.date_seen == date.today(),
                )
            ).first()
            if existing_today is not None:
                existing_today.price = price
                existing_today.bottle_size_ml = bottle_size_ml
                existing_today.raw_text = _clean_name(raw_name)
                session.add(existing_today)
            else:
                session.add(
                    Listing(
                        wine_vintage_id=vintage.id,
                        source=SOURCE,
                        source_type="restaurant",
                        raw_text=_clean_name(raw_name),
                        price=price,
                        currency="USD",
                        bottle_size_ml=bottle_size_ml,
                        date_seen=date.today(),
                    )
                )
            n_listings += 1

        session.commit()

    return {
        "products_seen": len(raw_products),
        "wines_created": n_created_wines,
        "vintages_created": n_created_vintages,
        "vintages_already_known": n_updated,
        "listings_upserted": n_listings,
    }


if __name__ == "__main__":
    result = ingest()
    print(result)
