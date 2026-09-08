import pytest

from app.scoring import (
    discount_pct,
    expected_price,
    is_deal,
    normalize_to_750ml,
    score_listing,
)


def test_normalize_to_750ml_same_size():
    assert normalize_to_750ml(100.0, 750) == 100.0


def test_normalize_to_750ml_magnum():
    # a 1500ml magnum priced at 100 is equivalent to a 750ml priced at 50
    assert normalize_to_750ml(100.0, 1500) == 50.0


def test_normalize_to_750ml_half_bottle():
    assert normalize_to_750ml(50.0, 375) == 100.0


def test_normalize_to_750ml_rejects_nonpositive_size():
    with pytest.raises(ValueError):
        normalize_to_750ml(10.0, 0)


def test_expected_price_auction_equals_reference():
    assert expected_price(100.0, "auction") == 100.0


def test_expected_price_restaurant_applies_markup():
    assert expected_price(100.0, "restaurant", restaurant_markup=2.5) == 250.0


def test_discount_pct_cheaper_is_positive():
    assert discount_pct(80.0, 100.0) == pytest.approx(0.2)


def test_discount_pct_pricier_is_negative():
    assert discount_pct(120.0, 100.0) == pytest.approx(-0.2)


def test_discount_pct_zero_expected_price_is_safe():
    assert discount_pct(50.0, 0.0) == 0.0


def test_is_deal_threshold():
    assert is_deal(0.15, threshold=0.15) is True
    assert is_deal(0.14, threshold=0.15) is False


def test_score_listing_auction_deal():
    score = score_listing(
        listing_price=80.0,
        listing_bottle_size_ml=750,
        reference_price=100.0,
        reference_bottle_size_ml=750,
        source_type="auction",
    )
    assert score.discount_pct == pytest.approx(0.2)
    assert score.is_deal is True


def test_score_listing_restaurant_at_expected_markup_is_not_a_deal():
    # restaurant priced right at the expected 2.5x markup is fairly priced, not a deal
    score = score_listing(
        listing_price=250.0,
        listing_bottle_size_ml=750,
        reference_price=100.0,
        reference_bottle_size_ml=750,
        source_type="restaurant",
    )
    assert score.expected_price_750 == 250.0
    assert score.is_deal is False


def test_score_listing_restaurant_deal_below_expected_markup():
    # restaurant priced at 1.5x retail is well under the 2.5x expected markup
    score = score_listing(
        listing_price=150.0,
        listing_bottle_size_ml=750,
        reference_price=100.0,
        reference_bottle_size_ml=750,
        source_type="restaurant",
    )
    assert score.is_deal is True


def test_score_listing_normalizes_bottle_sizes_independently():
    # listing is a magnum (1500ml) at 150, reference is a standard 750ml at 100
    # -> listing normalized to 75/750ml, reference stays 100/750ml -> 25% cheaper
    score = score_listing(
        listing_price=150.0,
        listing_bottle_size_ml=1500,
        reference_price=100.0,
        reference_bottle_size_ml=750,
        source_type="auction",
    )
    assert score.listing_price_750 == pytest.approx(75.0)
    assert score.discount_pct == pytest.approx(0.25)
