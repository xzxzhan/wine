# Underpriced Wine Finder

Find wines priced below their Wine-Searcher reference price at auction (K&L Wines)
or on restaurant wine lists.

## Status: Phase 0

Data model + manual entry + deal-scoring logic, running as a local FastAPI app
with SQLite. No scraping or PDF parsing yet — those are later phases. The goal
of this phase is to validate the comparison math (bottle-size normalization,
restaurant markup expectations, auction discount thresholds) with data you
enter by hand.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/wines

1. Add a wine + vintage.
2. Add a reference price for it (what Wine-Searcher says it's worth).
3. Add one or more listings (an auction lot or a restaurant wine-list line)
   for the same vintage.
4. Check http://127.0.0.1:8000/deals — listings priced below the expected
   price are highlighted.

## How "underpriced" is decided

- **Auctions** are expected to trade near the Wine-Searcher reference price.
  A listing is a deal if it's >=15% below reference (`DEFAULT_DEAL_THRESHOLD`
  in `app/scoring.py`).
- **Restaurants** are expected to mark up over retail (default 2.5x,
  `DEFAULT_RESTAURANT_MARKUP`). A listing is a deal if it's >=15% below
  *that expected marked-up price*, not below raw retail.
- All prices are normalized to a 750ml-equivalent before comparing, so a
  magnum or half-bottle listing compares fairly against a 750ml reference.

See `app/scoring.py` for the scoring logic and `tests/test_scoring.py` for
the behavior it's expected to satisfy.

## Data model

- `Wine` — producer, wine name, region
- `WineVintage` — a specific vintage year + bottle size of a `Wine`
- `ReferencePrice` — a Wine-Searcher price snapshot for a `WineVintage`
- `Listing` — an observed price for a `WineVintage` from an auction or
  restaurant, with the original raw text kept for future re-matching
- `WineAlias` — (unused so far) will map raw text patterns to a
  `WineVintage` once automated parsing/matching is built

## Roadmap

- **Phase 1**: restaurant PDF upload -> text/OCR extraction -> line parsing
  -> fuzzy match to existing wines, with a review queue for low-confidence
  matches.
- **Phase 2**: K&L auction scraper (checking `robots.txt`/ToS first) with
  scheduled refresh.
- **Phase 3**: deals dashboard polish (filters, sorting, alerts).
- **Phase 4**: revisit Wine-Searcher access (Pro API vs. manual entry vs.
  a scraper module) behind the existing pluggable reference-price interface
  — a decision that doesn't block anything above.
