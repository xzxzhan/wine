"""Loads Wine-Searcher reference prices from a CSV keyed by external_ref
(the stable product id from an automated ingestion source, e.g.
"plumedhorse:3225") and upserts them as ReferencePrice rows.

Why a CSV instead of a live lookup: Wine-Searcher blocks automated fetches
(confirmed 403 on direct requests), so reference prices are currently
collected via a human/agent-assisted search pass rather than a live API
call. This loader is the seam where that data enters the app -- swap it
for a real Wine-Searcher Pro API call later without changing anything
downstream (scoring, the deals view) since both just read ReferencePrice
rows.
"""
import csv
import sys
from datetime import date
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import ReferencePrice, WineVintage

DEFAULT_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "reference_prices_plumedhorse.csv"


def load(csv_path: Path = DEFAULT_CSV) -> dict:
    init_db()
    n_loaded = n_skipped_no_price = n_skipped_no_vintage = 0

    with Session(engine) as session, open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            external_ref = row["external_ref"].strip()
            price_str = row["price_usd"].strip()

            vintage = session.exec(
                select(WineVintage).where(WineVintage.external_ref == external_ref)
            ).first()
            if vintage is None:
                n_skipped_no_vintage += 1
                continue

            if not price_str:
                n_skipped_no_price += 1
                continue

            # Replace any existing wine-searcher reference for this vintage
            # so re-running the loader keeps prices fresh rather than piling up.
            existing = session.exec(
                select(ReferencePrice).where(
                    ReferencePrice.wine_vintage_id == vintage.id,
                    ReferencePrice.source == "wine-searcher",
                )
            ).all()
            for e in existing:
                session.delete(e)

            session.add(
                ReferencePrice(
                    wine_vintage_id=vintage.id,
                    source="wine-searcher",
                    price_type="avg_retail",
                    price=float(price_str),
                    currency="USD",
                    bottle_size_ml=int(row["bottle_size_ml"]),
                    confidence=row["confidence"],
                    note=row["note"] or None,
                    date_captured=date.today(),
                )
            )
            n_loaded += 1

        session.commit()

    return {
        "loaded": n_loaded,
        "skipped_no_price": n_skipped_no_price,
        "skipped_no_matching_vintage": n_skipped_no_vintage,
    }


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    print(load(path))
