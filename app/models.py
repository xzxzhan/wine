from datetime import date
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def normalize_name(producer: str, wine_name: str) -> str:
    return " ".join(f"{producer} {wine_name}".lower().split())


class Wine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    producer: str
    wine_name: str
    region: Optional[str] = None
    normalized_name: str = Field(index=True)

    vintages: List["WineVintage"] = Relationship(back_populates="wine")


class WineVintage(SQLModel, table=True):
    """A wine+vintage-year identity. Bottle size is NOT stored here: the same
    wine+vintage can be priced in multiple formats (375ml, 750ml, magnum),
    each with its own price, so bottle size lives on ReferencePrice/Listing.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    wine_id: int = Field(foreign_key="wine.id")
    vintage_year: Optional[int] = None  # None = non-vintage (NV)
    external_ref: Optional[str] = Field(default=None, index=True)
    # Stable id from an automated source (e.g. "plumedhorse:3225"), used to
    # re-match on re-ingestion without needing fuzzy text matching.

    wine: Wine = Relationship(back_populates="vintages")
    reference_prices: List["ReferencePrice"] = Relationship(back_populates="wine_vintage")
    listings: List["Listing"] = Relationship(back_populates="wine_vintage")


class ReferencePrice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    wine_vintage_id: int = Field(foreign_key="winevintage.id")
    source: str = "wine-searcher"
    price_type: str = "avg_retail"  # avg_retail | avg_auction
    price: float
    currency: str = "USD"
    bottle_size_ml: int = 750
    confidence: str = "medium"  # high | medium | low -- how sure we are this is the right wine/vintage
    note: Optional[str] = None  # why confidence isn't "high", or match caveats
    date_captured: date = Field(default_factory=date.today)

    wine_vintage: WineVintage = Relationship(back_populates="reference_prices")


class Listing(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    wine_vintage_id: Optional[int] = Field(default=None, foreign_key="winevintage.id")
    source: str  # e.g. "klwines-auction", "restaurant:French Laundry"
    source_type: str  # "auction" | "restaurant"
    raw_text: Optional[str] = None
    price: float
    currency: str = "USD"
    bottle_size_ml: int = 750
    date_seen: date = Field(default_factory=date.today)

    wine_vintage: Optional[WineVintage] = Relationship(back_populates="listings")


class WineAlias(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    raw_text_pattern: str = Field(index=True)
    wine_vintage_id: int = Field(foreign_key="winevintage.id")
