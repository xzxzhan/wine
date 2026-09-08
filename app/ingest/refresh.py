"""Runs the full Plumed Horse refresh: pull current listings from both
sources (the small WooCommerce to-go shop and the full BinWise sommelier
list), then reload Wine-Searcher reference prices from the seed CSV.
"""
from app.ingest import binwise, load_references, plumedhorse


def refresh_plumedhorse() -> dict:
    togo_result = plumedhorse.ingest()
    cellar_result = binwise.ingest()
    reference_result = load_references.load()
    return {
        "togo_listings": togo_result,
        "cellar_listings": cellar_result,
        "references": reference_result,
    }


if __name__ == "__main__":
    print(refresh_plumedhorse())
