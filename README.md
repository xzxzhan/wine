# Underpriced Wine Finder

Finds wines priced below their Wine-Searcher market price. Working
end-to-end for one restaurant so far: **Plumed Horse** (Saratoga, CA).

## Status

Automated ingestion, incremental reference-price research:

1. **Listings** — two sources, both fully automated, no scraping-ToS issues:
   - `app/ingest/plumedhorse.py` — a small ~20-bottle "to-go" retail
     selection, from Plumed Horse's public WooCommerce Store API.
   - `app/ingest/binwise.py` — the *real* sommelier cellar list, 2,418
     wines (1,595 red + 823 white). It's not on the WordPress site at all
     — Plumed Horse embeds it via plain iframes from a third-party
     wine-list host, BinWise, as static server-rendered HTML:
     `hub.binwise.com/Winelists/The-Plumed-Horse-{Red,White}-Wine-List.html`
2. **Reference prices** — `data/reference_prices_plumedhorse.csv`, filled
   in incrementally via search-assisted research (see methodology below),
   priciest wines first (`app/ingest/worklist.py`). Only 43 of 2,436 wines
   are covered as of the last research pass — this is genuinely
   incomplete and grows over time, not a bug.
3. `app/routers/deals.py` compares the two and `/deals` shows wines
   **below market price**, sorted by how far below.

Generalizing beyond Plumed Horse (new restaurants, K&L auctions, a real
fuzzy-matching review queue) is future work — see Roadmap.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 — on a fresh/empty database it
auto-bootstraps on startup (pulls current listings from both sources +
loads the reference-price CSV). To pull fresh listings later, click
**"Refresh from Plumed Horse"** on the page, or run directly:

```bash
python -m app.ingest.plumedhorse       # to-go shop listings
python -m app.ingest.binwise           # full cellar list (2,400+ wines)
python -m app.ingest.load_references   # loads WS reference prices from the CSV
python -m app.ingest.worklist [N]      # prints the top-N wines still needing research, priciest first
```

Re-running is safe/idempotent — both ingestors upsert by a stable
`external_ref` rather than creating duplicates.

## Automated reference-price research (Google Custom Search)

Manually searching for each wine (as done for the first ~59 wines) doesn't
scale to 2,400+. `app/ingest/search_reference_prices.py` automates it
using the Google Custom Search JSON API — no agent/human in the loop.
Wine-Searcher's own pages contain literal text like `Avg Price (ex-tax)
$240 / 750ml`, which Google indexes verbatim into the search snippet; the
script regexes that pattern directly out of wine-searcher.com results and
applies the same California > USA > global region-preference policy
described above.

**One-time setup** (needs your own Google account — free tier covers 100
queries/day; full 2,400-wine coverage costs roughly $0-12 total at $5 per
1,000 queries beyond that, vs. Wine-Searcher Pro's $335/month):

1. https://console.cloud.google.com/ → create/select a project → APIs &
   Services → Library → enable **"Custom Search API"**
2. APIs & Services → Credentials → Create Credentials → API Key
3. https://programmablesearchengine.google.com/ → create a search engine,
   set it to **"Search the entire web"** → copy its **Search engine ID** (cx)
4. `export GOOGLE_SEARCH_API_KEY=...` and `export GOOGLE_SEARCH_CSE_ID=...`

**Usage:**

```bash
python -m app.ingest.search_reference_prices --limit 90 --min-price 100
```

Respects the same 2-month staleness policy as everything else (via
`build_worklist()`), so re-running never re-queries a wine that's still
fresh. `--limit` caps how many wines it researches per run (default 90,
under the 100/day free tier); `--min-price` skips cheap wines to
prioritize the highest-value ones first; `--sleep` controls the delay
between queries (default 1s).

## How "below market price" is decided

For each wine, `app/scoring.py:below_market_pct()` normalizes both the
listing price and the Wine-Searcher reference price to a 750ml-equivalent
(so a half-bottle or magnum listing compares fairly against a
standard-bottle reference) and computes `(reference - listing) /
reference`. Positive means the restaurant is charging **less** than the
reference — a literal comparison, no assumption about what markup a
restaurant "should" charge.

## Reference-price methodology (what counts as "market price")

Wine-Searcher blocks automated fetches directly (confirmed 403) and its
ToS prohibits scraping, and there's no per-store itemized data available
without a paid Pro subscription. What's actually achievable via
search-assisted lookup, best to worst, and how it's labeled in the
`confidence`/`note` columns of the CSV:

1. **Itemized average of the lowest CA/US-shippable store prices**
   (`confidence: high`) — when individual retailer prices surface (e.g.
   "GRW Wine Collection $3995, Malibu Liquor & Wine $3999.95, WineBank
   $4200"), average up to 3 of the lowest. This is the real target: what
   it would actually cost to buy the wine shipped to California. Rare in
   practice — mostly surfaces for very famous, heavily-indexed wines.
2. **Wine-Searcher's own California- or USA-region-filtered average**
   (`confidence: medium`) — not itemized, but excludes overseas-only
   markets. This is the common case.
3. **Wine-Searcher's global average** (`confidence: low`) — used only as
   a last resort when no US/CA-specific figure exists, explicitly noted
   as "not available in CA/USA" since it can include pricing from markets
   (Europe especially) the diner can't actually buy from. A global-only
   figure is a real methodological compromise, not a preference — it's
   there so the wine isn't silently dropped, but should be trusted less.
4. **No usable price found at all** — left blank, shown in "Needs review"
   on `/deals` rather than guessed at.

`confidence: none` is reserved for cases where the wine itself doesn't
seem to exist as described (see "known data issues" below) — not a
pricing gap but a listing/matching problem.

`app/ingest/load_references.py` is the seam: swap it for a real
Wine-Searcher Pro API call later and nothing downstream (scoring,
`/deals`) needs to change, since both only ever read `ReferencePrice`
rows.

### The local price cache and its 2-month TTL

`ReferencePrice.date_captured` is a "last updated" timestamp.
`app/ingest/worklist.py` (`is_stale_or_missing`) treats a wine as needing
a fresh Wine-Searcher lookup only if it's never been looked up, or its
most recent lookup is 60+ days old — so re-running research doesn't
re-query wines that are still fresh. This *is* the local Wine-Searcher
price database the project needs; there's no separate cache structure.

### Known data issues found so far

- One listing (`CAYMUS, 2022 (1000 ml)` at **$98,500**) is almost
  certainly a data-entry error on the restaurant's own list — real
  Wine-Searcher pricing for 2022 Caymus tops out around $88-93/750ml, so
  even at 1000ml this should be roughly $985, not $98,500. Left as-is
  (not "corrected") since it's the restaurant's actual listed price; it
  will just show as a wildly-above-market outlier, which is accurate.
- 4 of the original 20 to-go wines have no usable reference at all —
  see git history for details (a nonexistent bottling, a renamed
  second-label wine, etc.) — the real-world wine-matching problem the
  original plan flagged, showing up immediately on real data.

## Data model

- `Wine` — producer, wine name, region (display only; not used for matching)
- `WineVintage` — a wine + vintage year. Has an `external_ref` — the
  stable id from an automated source (a WooCommerce product id, or for
  BinWise a content hash of the listing text, since BinWise exposes no
  real id) — used to re-match on refresh without fuzzy text matching.
- `ReferencePrice` — a Wine-Searcher price snapshot for a `WineVintage`,
  with its own `bottle_size_ml`, `confidence`, `note`, and
  `date_captured` (the cache timestamp)
- `Listing` — an observed price for a `WineVintage` from a restaurant (or
  auction), with its own `bottle_size_ml` and the original raw text kept
- `WineAlias` — (unused so far) for a future free-text fuzzy-matching
  pipeline, once this generalizes to restaurants without any structured
  source at all (e.g. a PDF-only wine list)

Bottle size lives on `ReferencePrice`/`Listing`, not `WineVintage` — the
same wine+vintage can appear in multiple formats (375ml, 750ml, magnum),
each independently priced.

## Manual entry (still supported)

The original manual-entry flow (`/wines` — add wines/vintages/reference
prices/listings by hand) still works, useful for testing or for a
restaurant without any structured source.

## Roadmap

- **Keep researching reference prices**: 43/2,436 wines covered as of the
  last pass. Run `python -m app.ingest.worklist` for the next priciest
  batch still needing a lookup.
- **Generalize ingestion**: most restaurants won't have a BinWise/
  WooCommerce API — the common case will be a PDF wine list, needing
  text/OCR extraction and fuzzy matching (`WineAlias`) instead of a
  stable `external_ref`.
- **K&L auction listings**: same idea as Plumed Horse's ingestion — check
  `robots.txt`/ToS, then pull structured auction data on a schedule.
- **Multi-restaurant / multi-source dashboard**: `/deals` currently only
  shows Plumed Horse; generalize once a second source exists.
- **Wine-Searcher access**: revisit a Pro API subscription if research
  volume outgrows search-assisted lookups.
