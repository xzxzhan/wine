"""Runs the full Plumed Horse refresh: pull current listings, then reload
Wine-Searcher reference prices from the seed CSV.
"""
from app.ingest import load_references, plumedhorse


def refresh_plumedhorse() -> dict:
    listing_result = plumedhorse.ingest()
    reference_result = load_references.load()
    return {"listings": listing_result, "references": reference_result}


if __name__ == "__main__":
    print(refresh_plumedhorse())
