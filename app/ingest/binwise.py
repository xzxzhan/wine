"""Pulls Plumed Horse's actual sommelier wine list, which lives on BinWise
(a third-party wine-list hosting service), not in the WooCommerce shop.

Plumed Horse embeds it publicly via two plain iframes on
https://plumedhorse.com/wine/ -- these are static, server-rendered HTML
pages (no JS execution needed), meant to be read by any visitor's browser:

    https://hub.binwise.com/Winelists/The-Plumed-Horse-Red-Wine-List.html
    https://hub.binwise.com/Winelists/The-Plumed-Horse-White-Wine-List.html

The WooCommerce "Red/White Bottles" categories (see plumedhorse.py) are a
small, separate ~20-bottle to-go retail selection -- not this list.

BinWise gives no stable per-wine id, so external_ref here is a content
hash of (color, section, subsection, wine name text, format text): stable
across price updates on refresh, changes only if the listing text itself
changes.
"""
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Listing, Wine, WineVintage, normalize_name

BINWISE_URLS = {
    "red": "https://hub.binwise.com/Winelists/The-Plumed-Horse-Red-Wine-List.html",
    "white": "https://hub.binwise.com/Winelists/The-Plumed-Horse-White-Wine-List.html",
}
SOURCE = "restaurant:Plumed Horse"

FORMAT_ML = {
    "half": 375,
    "half bottle": 375,
    "demi": 375,
    "bottle": 750,
    "magnum": 1500,
    "double magnum": 3000,
    "jeroboam": 3000,
    "rehoboam": 4500,
    "methuselah": 6000,
    "imperial": 6000,
    "salmanazar": 9000,
    "balthazar": 12000,
    "nebuchadnezzar": 15000,
}
ML_RE = re.compile(r"(\d+)\s*ml", re.IGNORECASE)
TRAILING_VINTAGE_RE = re.compile(r",?\s*(\d{4})\s*\.*\s*$")


@dataclass
class RawRow:
    color: str
    section: str
    subsection: str
    name_text: str
    format_text: str
    price: float


def _font_size(tr) -> Optional[int]:
    span = tr.find("span")
    if span is None:
        return None
    style = span.get("style", "") or span.get("STYLE", "")
    m = re.search(r"font-size:\s*(\d+)", style, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_price(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_bottle_size_ml(format_text: str) -> int:
    if not format_text:
        return 750
    text = format_text.strip().lower()
    m = ML_RE.search(text)
    if m:
        return int(m.group(1))
    for key, ml in FORMAT_ML.items():
        if key in text:
            return ml
    return 750


def parse_wine_name(raw_name: str) -> tuple[Optional[int], str, str]:
    """Best-effort split of a BinWise wine-list entry into
    (vintage_year, producer, wine_name). Display only -- matching uses
    external_ref, not this text. Vintage is trailing here (unlike the
    WooCommerce titles, which lead with it)."""
    name = re.sub(r"\s+", " ", raw_name).strip()

    vintage_year = None
    m = TRAILING_VINTAGE_RE.search(name)
    rest = name
    if m:
        vintage_year = int(m.group(1))
        rest = name[: m.start()].strip().rstrip(",").strip()

    before_comma = rest.split(",", 1)[0].strip()
    wine_name = rest[len(before_comma):].strip(" ,") or rest
    producer = before_comma or "Unknown"

    return vintage_year, producer, wine_name or rest


def fetch_rows(color: str) -> list[RawRow]:
    resp = httpx.get(
        BINWISE_URLS[color],
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; wine-underpriced-finder/0.1)"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    rows: list[RawRow] = []
    section = subsection = ""
    for tr in soup.find_all("tr"):
        if tr.find("table"):
            continue  # layout wrapper row, not a leaf row
        tds = tr.find_all("td", recursive=False)
        if len(tds) == 1:
            size = _font_size(tr)
            text = tds[0].get_text(strip=True)
            if size is not None and size >= 24:
                continue  # page title, not a real section
            if size is not None and size >= 18:
                section, subsection = text, ""
            else:
                subsection = text
        elif len(tds) == 3:
            name_text = tds[0].get_text(" ", strip=True)
            format_text = tds[1].get_text(strip=True)
            price = parse_price(tds[2].get_text(strip=True))
            if not name_text or price is None:
                continue
            rows.append(RawRow(color, section, subsection, name_text, format_text, price))

    return rows


def _external_ref(row: RawRow) -> str:
    key = f"{row.color}|{row.section}|{row.subsection}|{row.name_text}|{row.format_text}".lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"plumedhorse-binwise:{digest}"


def ingest() -> dict:
    init_db()
    all_rows: list[RawRow] = []
    for color in BINWISE_URLS:
        all_rows.extend(fetch_rows(color))

    n_created = n_known = n_listings = 0

    with Session(engine) as session:
        existing_refs = {
            v.external_ref: v.id
            for v in session.exec(
                select(WineVintage).where(WineVintage.external_ref.isnot(None))
            ).all()
            if v.external_ref and v.external_ref.startswith("plumedhorse-binwise:")
        }

        for row in all_rows:
            ext_ref = _external_ref(row)
            vintage_id = existing_refs.get(ext_ref)

            if vintage_id is None:
                vintage_year, producer, wine_name = parse_wine_name(row.name_text)
                region = row.subsection or row.section or None
                wine = Wine(
                    producer=producer,
                    wine_name=wine_name,
                    region=region,
                    normalized_name=normalize_name(producer, wine_name),
                )
                session.add(wine)
                session.flush()

                vintage = WineVintage(
                    wine_id=wine.id, vintage_year=vintage_year, external_ref=ext_ref
                )
                session.add(vintage)
                session.flush()
                vintage_id = vintage.id
                existing_refs[ext_ref] = vintage_id
                n_created += 1
            else:
                n_known += 1

            bottle_size_ml = parse_bottle_size_ml(row.format_text)
            raw_text = row.name_text + (f" ({row.format_text})" if row.format_text else "")

            existing_today = session.exec(
                select(Listing).where(
                    Listing.wine_vintage_id == vintage_id,
                    Listing.source == SOURCE,
                    Listing.date_seen == date.today(),
                    Listing.bottle_size_ml == bottle_size_ml,
                )
            ).first()
            if existing_today is not None:
                existing_today.price = row.price
                existing_today.raw_text = raw_text
                session.add(existing_today)
            else:
                session.add(
                    Listing(
                        wine_vintage_id=vintage_id,
                        source=SOURCE,
                        source_type="restaurant",
                        raw_text=raw_text,
                        price=row.price,
                        currency="USD",
                        bottle_size_ml=bottle_size_ml,
                        date_seen=date.today(),
                    )
                )
            n_listings += 1

        session.commit()

    return {
        "rows_seen": len(all_rows),
        "wines_created": n_created,
        "wines_already_known": n_known,
        "listings_upserted": n_listings,
    }


if __name__ == "__main__":
    print(ingest())
