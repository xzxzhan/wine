from datetime import date, timedelta

from app.ingest.worklist import STALE_DAYS, is_stale_or_missing
from app.models import ReferencePrice


def _ref(days_ago: int, source: str = "wine-searcher") -> ReferencePrice:
    return ReferencePrice(
        wine_vintage_id=1,
        source=source,
        price=100.0,
        date_captured=date.today() - timedelta(days=days_ago),
    )


def test_missing_reference_is_stale():
    assert is_stale_or_missing([]) is True


def test_fresh_reference_is_not_stale():
    assert is_stale_or_missing([_ref(1)]) is False


def test_reference_just_under_threshold_is_not_stale():
    assert is_stale_or_missing([_ref(STALE_DAYS - 1)]) is False


def test_reference_at_threshold_is_stale():
    assert is_stale_or_missing([_ref(STALE_DAYS)]) is True


def test_reference_over_threshold_is_stale():
    assert is_stale_or_missing([_ref(STALE_DAYS + 10)]) is True


def test_uses_most_recent_of_several_references():
    refs = [_ref(200), _ref(5), _ref(100)]
    assert is_stale_or_missing(refs) is False


def test_ignores_non_wine_searcher_sources():
    # a manually-entered reference from some other source shouldn't count
    # as a fresh wine-searcher lookup
    assert is_stale_or_missing([_ref(1, source="manual")]) is True
