import pytest

from app.ingest.binwise import parse_bottle_size_ml, parse_price, parse_wine_name


def test_parse_price_plain():
    assert parse_price("175") == 175.0


def test_parse_price_with_comma():
    assert parse_price("1,250") == 1250.0


def test_parse_price_empty():
    assert parse_price("") is None


def test_parse_price_garbage():
    assert parse_price("call for price") is None


def test_parse_bottle_size_default():
    assert parse_bottle_size_ml("") == 750


def test_parse_bottle_size_magnum():
    assert parse_bottle_size_ml("magnum") == 1500


def test_parse_bottle_size_explicit_ml():
    assert parse_bottle_size_ml("1000 ml") == 1000


def test_parse_bottle_size_methuselah():
    assert parse_bottle_size_ml("methuselah") == 6000


def test_parse_wine_name_trailing_vintage():
    vintage, producer, wine_name = parse_wine_name(
        'ALOFT, "Cold Springs Vineyard," Howell Mountain, 2009'
    )
    assert vintage == 2009
    assert producer == "ALOFT"


def test_parse_wine_name_no_vintage_is_nv():
    vintage, producer, wine_name = parse_wine_name("VEUVE CLICQUOT, Brut Yellow Label")
    assert vintage is None
    assert producer == "VEUVE CLICQUOT"
