# Underpriced Wine Finder

Finds wines priced below their Wine-Searcher average retail price. Working
end-to-end for one restaurant so far: **Plumed Horse** (Saratoga, CA).

## Status

Automated, working pipeline for Plumed Horse:

1. `app/ingest/plumedhorse.py` pulls the current wine list from Plumed
   Horse's public WooCommerce Store API (the same data that powers
   https://plumedhorse.com/wine/) — fully automated, no scraping involved,
   safe to re-run any time.
2. `data/reference_prices_plumedhorse.csv` holds Wine-Searcher average
   retail prices for those wines, collected via a search-assisted lookup
   pass (see "Why reference prices are a CSV, not a live call" below).
3. `app/routers/deals.py` compares the two and the `/deals` page shows
   wines **below market price**, sorted by how far below, with everything
   else visible but secondary.

Generalizing beyond Plumed Horse (new restaurants, K&L auctions, a real
fuzzy-matching review queue) is future work — see Roadmap.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/deals — it's empty until you run the
ingestion once:

```bash
python -m app.ingest.plumedhorse       # pulls current listings
python -m app.ingest.load_references   # loads WS reference prices from the CSV
```

or just click **"Refresh from Plumed Horse"** on the `/deals` page, which
does both. Re-running is safe/idempotent — it upserts by the wine's stable
product id rather than creating duplicates.

## How "below market price" is decided

For each wine, `app/scoring.py:below_market_pct()` normalizes both the
listing price and the Wine-Searcher reference price to a 750ml-equivalent
(so a half-bottle listing compares fairly against a standard-bottle
reference) and computes `(reference - listing) / reference`. Positive means
the restaurant is charging **less** than Wine-Searcher's average retail —
a literal comparison, with no assumption baked in about what markup a
restaurant "should" charge.

(`scoring.py` also has a markup-adjusted `score_listing()`/`expected_price()`
path left over from early design, useful later if this generalizes to many
restaurants where "is this a good price *for a restaurant*" — i.e. relative
to an expected 2-3x markup — becomes the more useful question than "is this
below retail." The `/deals` page currently uses the literal comparison.)

## Why reference prices are a CSV, not a live call

Wine-Searcher blocks automated fetches (confirmed 403 on a direct request)
and their ToS prohibits scraping. There's no way for this app's backend to
look up a price live without either a paid Wine-Searcher Pro API
subscription or violating their terms. What's implemented instead:
`data/reference_prices_plumedhorse.csv`, populated via a search-assisted
pass (an agent or person searching for "<wine> wine-searcher average
price" and reading indexed snippets — not hitting wine-searcher.com
directly) — with a `confidence` and `note` column per entry, since the
match often isn't exact:

- **high** — vintage-specific match, no ambiguity
- **medium** — right wine, but the price is an all-vintages average, a
  currency conversion, or a same-family second-label guess
- **low** — plausible but uncertain match (ambiguous vineyard/cuvée naming)
- blank price — no reliable Wine-Searcher price found at all; shown in the
  "Needs review" section on `/deals` rather than silently dropped

4 of the current 20 Plumed Horse wines have no usable reference at all —
one doesn't match any real bottling from that producer (likely a data
error on the restaurant's own list), one is a renamed second-label wine
with no price under either name for that vintage, and two have no
confident Wine-Searcher match. This is the real-world wine-matching
problem the original plan flagged, showing up immediately on real data.

`app/ingest/load_references.py` is the seam: swap it for a real
Wine-Searcher API call later and nothing downstream (scoring, `/deals`)
needs to change, since both only ever read `ReferencePrice` rows.

## Data model

- `Wine` — producer, wine name, region (display only; not used for matching)
- `WineVintage` — a wine + vintage year. Has an `external_ref` (e.g.
  `"plumedhorse:3225"`) — the stable id from an automated source, used to
  re-match on refresh without fuzzy text matching.
- `ReferencePrice` — a Wine-Searcher price snapshot for a `WineVintage`,
  with its own `bottle_size_ml`, `confidence`, and `note`
- `Listing` — an observed price for a `WineVintage` from a restaurant (or
  auction), with its own `bottle_size_ml` and the original raw text kept
- `WineAlias` — (unused so far) for a future free-text fuzzy-matching
  pipeline, once this generalizes to restaurants without a public API

Bottle size lives on `ReferencePrice`/`Listing`, not `WineVintage` — the
same wine+vintage can appear in multiple formats (375ml, 750ml, magnum),
each independently priced. An earlier version stored it on the vintage and
incorrectly assumed a listing and its reference always shared the same
bottle size — caught when the Pierre Gimonnet half-bottle test case showed
an inflated discount.

## Manual entry (still supported)

The original manual-entry flow (`/wines` — add wines/vintages/reference
prices/listings by hand) still works, useful for testing or for a
restaurant without a public product API.

## Roadmap

- **Generalize ingestion**: most restaurants don't expose a WooCommerce
  API like Plumed Horse does — the common case will be a PDF wine list,
  needing text/OCR extraction and fuzzy matching (`WineAlias`) instead of
  a stable `external_ref`.
- **K&L auction listings**: same idea as Plumed Horse's ingestion — check
  `robots.txt`/ToS, then pull structured auction data on a schedule.
- **Multi-restaurant / multi-source dashboard**: `/deals` currently only
  shows Plumed Horse; generalize once a second source exists.
- **Wine-Searcher access**: revisit a Pro API subscription if this scales
  beyond occasional search-assisted lookups.
