"""Unattended Wine-Searcher reference-price research via the Google Custom
Search JSON API -- no agent/human in the loop required, unlike the earlier
search-assisted passes.

Setup (one-time, see README.md "Automated reference-price research"):
  1. Enable the "Custom Search API" on a Google Cloud project, create an
     API key.
  2. Create a Programmable Search Engine at
     https://programmablesearchengine.google.com/ set to "Search the
     entire web", copy its Search engine ID (cx).
  3. export GOOGLE_SEARCH_API_KEY=...
     export GOOGLE_SEARCH_CSE_ID=...

Why this works without an LLM summarizing anything: Wine-Searcher's own
pages contain literal text like "Avg Price (ex-tax) $240 / 750ml", which
Google indexes verbatim into the search result snippet. This script
regexes that pattern directly out of wine-searcher.com results -- more
reliable than reading an AI-paraphrased summary, since it's the actual
source text, not someone's retelling of it.

Region tiering mirrors the manual research methodology (see README):
prefer results whose URL/snippet indicates California or USA, average up
to 3 of them; fall back to untagged ("global") results only when no
US-region result exists, and label those low-confidence.
"""
import argparse
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx
from sqlmodel import Session

from app.db import engine, init_db
from app.ingest.worklist import WorklistItem, build_worklist
from app.models import ReferencePrice

GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

PRICE_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)\s*(?:/\s*750\s*ml)?", re.IGNORECASE)
CA_HINTS = ("california", "usa-ca", "/usa-ca")
USA_HINTS = ("usa", "united states", "/usa", " us ")

# Sanity bounds: reject obviously-wrong extractions (a "$5" from unrelated
# page furniture, or a >7-figure number from something that isn't a price).
MIN_PLAUSIBLE_PRICE = 10.0
MAX_PLAUSIBLE_PRICE = 200_000.0


@dataclass
class PriceCandidate:
    price: float
    region: str  # "california" | "usa" | "global"


def get_credentials() -> tuple[str, str]:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cse_id = os.environ.get("GOOGLE_SEARCH_CSE_ID")
    if not api_key or not cse_id:
        raise RuntimeError(
            "Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CSE_ID environment "
            "variables (see README.md 'Automated reference-price research')."
        )
    return api_key, cse_id


def search(query: str, api_key: str, cse_id: str) -> list[dict]:
    resp = httpx.get(
        GOOGLE_SEARCH_URL,
        params={"key": api_key, "cx": cse_id, "q": query, "num": 10},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def classify_region(text: str) -> str:
    lower = text.lower()
    if any(h in lower for h in CA_HINTS):
        return "california"
    if any(h in lower for h in USA_HINTS):
        return "usa"
    return "global"


def extract_price_candidate(item: dict) -> Optional[PriceCandidate]:
    """Pulls a plausible price out of one wine-searcher.com search result."""
    link = item.get("link", "")
    if "wine-searcher.com" not in link:
        return None
    text = f"{item.get('title', '')} {item.get('snippet', '')}"
    m = PRICE_RE.search(text)
    if not m:
        return None
    price = float(m.group(1).replace(",", ""))
    if not (MIN_PLAUSIBLE_PRICE <= price <= MAX_PLAUSIBLE_PRICE):
        return None
    return PriceCandidate(price=price, region=classify_region(text + " " + link))


def pick_reference(candidates: list[PriceCandidate]) -> Optional[dict]:
    """Applies the region-preference policy: California > USA > global,
    averaging up to 3 of the lowest within whichever tier is used."""
    for tier, confidence in (
        ("california", "medium"),
        ("usa", "medium"),
        ("global", "low"),
    ):
        tier_prices = sorted(c.price for c in candidates if c.region == tier)
        if not tier_prices:
            continue
        top3 = tier_prices[:3]
        avg = sum(top3) / len(top3)
        note = f"Auto-research (Google CSE): {len(top3)} wine-searcher.com snippet(s) tagged '{tier}', averaged"
        if tier == "global":
            note += " -- not available in CA/USA"
        return {"price": round(avg, 2), "confidence": confidence, "note": note}
    return None


def research_one(item: WorklistItem, api_key: str, cse_id: str) -> Optional[dict]:
    query = f"{item.raw_text} wine-searcher average price"
    results = search(query, api_key, cse_id)
    candidates = [c for c in (extract_price_candidate(r) for r in results) if c]
    return pick_reference(candidates)


def run(limit: int = 90, min_price: float = 0.0, sleep_seconds: float = 1.0) -> dict:
    api_key, cse_id = get_credentials()
    init_db()

    n_found = n_not_found = n_errors = 0
    with Session(engine) as session:
        worklist = build_worklist(session, limit=limit, min_price=min_price)
        for item in worklist:
            if not item.external_ref:
                continue
            try:
                result = research_one(item, api_key, cse_id)
            except httpx.HTTPStatusError as e:
                print(f"[error] {item.raw_text}: HTTP {e.response.status_code}")
                n_errors += 1
                if e.response.status_code == 429:
                    print("Quota exceeded, stopping.")
                    break
                time.sleep(sleep_seconds)
                continue

            if result is None:
                print(f"[no match] {item.raw_text}")
                n_not_found += 1
            else:
                from sqlmodel import select

                vintage_id = item.vintage_id
                for existing in session.exec(
                    select(ReferencePrice).where(
                        ReferencePrice.wine_vintage_id == vintage_id,
                        ReferencePrice.source == "wine-searcher",
                    )
                ).all():
                    session.delete(existing)
                session.add(
                    ReferencePrice(
                        wine_vintage_id=vintage_id,
                        source="wine-searcher",
                        price_type="avg_retail",
                        price=result["price"],
                        currency="USD",
                        bottle_size_ml=750,
                        confidence=result["confidence"],
                        note=result["note"],
                        date_captured=date.today(),
                    )
                )
                session.commit()
                print(f"[found] {item.raw_text}: ${result['price']:.2f} ({result['confidence']})")
                n_found += 1

            time.sleep(sleep_seconds)

    return {"found": n_found, "not_found": n_not_found, "errors": n_errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=90, help="max wines to research this run")
    parser.add_argument("--min-price", type=float, default=0.0, help="skip wines listed below this price")
    parser.add_argument("--sleep", type=float, default=1.0, help="seconds between queries")
    args = parser.parse_args()
    print(run(limit=args.limit, min_price=args.min_price, sleep_seconds=args.sleep))
