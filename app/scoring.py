"""Deal-scoring logic: compare a listing's price against a reference price.

Kept dependency-free from the DB layer so it's easy to unit test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DEFAULT_RESTAURANT_MARKUP = 2.5
DEFAULT_DEAL_THRESHOLD = 0.15  # flag if price is >=15% below expected


def normalize_to_750ml(price: float, bottle_size_ml: int) -> float:
    if bottle_size_ml <= 0:
        raise ValueError("bottle_size_ml must be positive")
    return price * (750 / bottle_size_ml)


def expected_price(
    reference_price: float,
    source_type: str,
    restaurant_markup: float = DEFAULT_RESTAURANT_MARKUP,
) -> float:
    """The price we'd *expect* to pay given the listing's context.

    Auctions are expected to trade near the reference price. Restaurants
    are expected to mark up over retail, so a restaurant price is only a
    "deal" relative to that expected markup, not raw retail.
    """
    if source_type == "restaurant":
        return reference_price * restaurant_markup
    return reference_price


def discount_pct(listing_price_750: float, expected_price_750: float) -> float:
    """Positive = listing is cheaper than expected. Negative = pricier."""
    if expected_price_750 <= 0:
        return 0.0
    return (expected_price_750 - listing_price_750) / expected_price_750


def is_deal(discount: float, threshold: float = DEFAULT_DEAL_THRESHOLD) -> bool:
    return discount >= threshold


@dataclass
class DealScore:
    listing_price_750: float
    reference_price_750: float
    expected_price_750: float
    discount_pct: float
    is_deal: bool


def score_listing(
    listing_price: float,
    listing_bottle_size_ml: int,
    reference_price: float,
    reference_bottle_size_ml: int,
    source_type: str,
    restaurant_markup: float = DEFAULT_RESTAURANT_MARKUP,
    deal_threshold: float = DEFAULT_DEAL_THRESHOLD,
) -> DealScore:
    listing_750 = normalize_to_750ml(listing_price, listing_bottle_size_ml)
    reference_750 = normalize_to_750ml(reference_price, reference_bottle_size_ml)
    expected_750 = expected_price(reference_750, source_type, restaurant_markup)
    discount = discount_pct(listing_750, expected_750)
    return DealScore(
        listing_price_750=listing_750,
        reference_price_750=reference_750,
        expected_price_750=expected_750,
        discount_pct=discount,
        is_deal=is_deal(discount, deal_threshold),
    )


def below_market_pct(
    listing_price: float,
    listing_bottle_size_ml: int,
    reference_price: float,
    reference_bottle_size_ml: int,
) -> float:
    """How far below the raw Wine-Searcher reference price a listing is.

    Unlike score_listing(), this applies no restaurant-markup assumption --
    it's a literal "is this priced below market" comparison. Positive means
    the listing is cheaper than the Wine-Searcher reference; negative means
    it's marked up over it (the normal case for a restaurant wine list).
    """
    listing_750 = normalize_to_750ml(listing_price, listing_bottle_size_ml)
    reference_750 = normalize_to_750ml(reference_price, reference_bottle_size_ml)
    return discount_pct(listing_750, reference_750)


def best_reference_price(reference_prices: list) -> Optional[object]:
    """Pick the most recent reference price when several exist for a vintage."""
    if not reference_prices:
        return None
    return max(reference_prices, key=lambda rp: rp.date_captured)
