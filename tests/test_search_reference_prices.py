import pytest

from app.ingest.search_reference_prices import (
    PriceCandidate,
    classify_region,
    extract_price_candidate,
    pick_reference,
)


def test_classify_region_california():
    assert classify_region("stores near you in California, USA") == "california"


def test_classify_region_usa():
    assert classify_region("Avg Price (ex-tax) $240 / 750ml in the USA") == "usa"


def test_classify_region_global_default():
    assert classify_region("Avg Price (ex-tax) EUR 61 / 750ml") == "global"


def test_extract_price_candidate_ignores_non_wine_searcher_links():
    item = {"link": "https://www.wine.com/product/x", "snippet": "$99.99"}
    assert extract_price_candidate(item) is None


def test_extract_price_candidate_parses_price_and_region():
    item = {
        "link": "https://www.wine-searcher.com/find/foo/1/usa-ca",
        "title": "Best local price for Foo - stores near you in California, USA",
        "snippet": "Avg Price (ex-tax) $135 / 750ml",
    }
    c = extract_price_candidate(item)
    assert c is not None
    assert c.price == 135.0
    assert c.region == "california"


def test_extract_price_candidate_rejects_no_price():
    item = {"link": "https://www.wine-searcher.com/find/foo", "snippet": "no price shown here"}
    assert extract_price_candidate(item) is None


def test_extract_price_candidate_rejects_implausible_price():
    item = {"link": "https://www.wine-searcher.com/find/foo", "snippet": "rated 95/100, $3 shipping"}
    # $3 is below MIN_PLAUSIBLE_PRICE
    assert extract_price_candidate(item) is None


def test_pick_reference_prefers_california_over_usa():
    candidates = [
        PriceCandidate(100.0, "usa"),
        PriceCandidate(50.0, "california"),
    ]
    result = pick_reference(candidates)
    assert result["price"] == 50.0
    assert result["confidence"] == "medium"


def test_pick_reference_averages_up_to_three_lowest_in_tier():
    candidates = [
        PriceCandidate(100.0, "california"),
        PriceCandidate(80.0, "california"),
        PriceCandidate(60.0, "california"),
        PriceCandidate(500.0, "california"),  # excluded, not one of the 3 lowest
    ]
    result = pick_reference(candidates)
    assert result["price"] == pytest.approx(80.0)


def test_pick_reference_falls_back_to_global_with_low_confidence():
    candidates = [PriceCandidate(200.0, "global")]
    result = pick_reference(candidates)
    assert result["price"] == 200.0
    assert result["confidence"] == "low"
    assert "not available in CA/USA" in result["note"]


def test_pick_reference_none_when_no_candidates():
    assert pick_reference([]) is None
