"""Catalog reads shared by the buyer and operations assistants."""

import re
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from merchant_agent import Listing, ListingDetails
from shopping_agent import Product, ProductDetails

from app.models.database import CatalogProduct


SELLABLE_STATUSES = ("active",)
_TOKEN = re.compile(r"[\w一-鿿]+", re.UNICODE)


def money(value: Optional[Decimal]) -> Optional[float]:
    return None if value is None else round(float(value), 4)


def trade_attributes(row: CatalogProduct) -> Dict[str, str]:
    """The listing attributes (a variant inherits its family's) plus the B2B terms every
    quote depends on: MOQ, production lead time and availability."""
    inherited = dict(row.parent.attributes_json or {}) if row.parent is not None else {}
    attributes = {str(k): str(v) for k, v in {**inherited, **(row.attributes_json or {})}.items()}
    attributes["moq"] = f"{row.moq} {attributes.get('unit', 'pcs')}"
    if row.lead_time_days:
        attributes["lead_time"] = f"{row.lead_time_days} days"
    attributes["availability"] = (
        "in stock" if stock_of(row) > 0 else f"made to order, {row.lead_time_days} days"
        if row.lead_time_days
        else "out of stock"
    )
    return attributes


def orderable(row: CatalogProduct) -> bool:
    """Stock on hand, or producible to order within a stated lead time."""
    return row.stock > 0 or bool(row.lead_time_days)


def stock_of(row: CatalogProduct) -> int:
    if row.variants:
        return sum(max(variant.stock, 0) for variant in row.variants)
    return max(row.stock, 0)


def to_product(row: CatalogProduct) -> Product:
    variants = [v for v in row.variants if v.status in SELLABLE_STATUSES]
    price = row.price
    if variants:
        priced = [v.price for v in variants if v.stock > 0] or [v.price for v in variants]
        price = min(priced)
    return Product(
        product_id=row.id,
        title=row.title,
        brand=row.brand,
        price=money(price) or 0.0,
        currency=row.currency,
        image_url=row.image_url,
        category=row.category,
        labels=list(row.labels_json or []),
        attributes=trade_attributes(row),
        in_stock=(any(orderable(v) for v in variants) if variants else orderable(row)),
        short_description=row.short_description,
        options=dict(row.options_json or {}) if variants else {},
        option_values=dict(row.option_values_json or {}),
        variant_of=row.parent_id,
    )


def to_details(row: CatalogProduct) -> ProductDetails:
    base = to_product(row)
    return ProductDetails(
        **base.model_dump(),
        long_description=row.long_description,
        specs={str(k): str(v) for k, v in (row.specs_json or {}).items()},
        variants=[
            to_product(variant) for variant in row.variants if variant.status in SELLABLE_STATUSES
        ],
    )


def content_quality(row: CatalogProduct) -> str:
    missing = missing_attributes(row)
    if not row.long_description or len(missing) >= 3:
        return "poor"
    if missing or len(row.short_description or "") < 40:
        return "needs_work"
    return "good"


REQUIRED_LISTING_ATTRIBUTES = ("material", "origin", "hs_code", "certifications", "packaging")


def missing_attributes(row: CatalogProduct) -> List[str]:
    attributes = row.attributes_json or {}
    return [name for name in REQUIRED_LISTING_ATTRIBUTES if not attributes.get(name)]


def listing_status(row: CatalogProduct) -> str:
    if row.status == "active" and stock_of(row) <= 0:
        return "out_of_stock"
    return row.status if row.status in ("active", "paused", "draft") else "paused"


def to_listing(row: CatalogProduct) -> Listing:
    product = to_product(row)
    return Listing(
        listing_id=row.id,
        title=row.title,
        status=listing_status(row),
        price=product.price,
        currency=row.currency,
        stock=stock_of(row),
        category=row.category,
        content_quality=content_quality(row),
        attributes=trade_attributes(row),
        image_url=row.image_url,
        short_description=row.short_description,
        options=product.options,
        option_values=product.option_values,
        variant_of=row.parent_id,
    )


def to_listing_details(row: CatalogProduct) -> ListingDetails:
    return ListingDetails(
        **to_listing(row).model_dump(),
        long_description=row.long_description,
        sales_last_30d=row.sales_last_30d,
        missing_attributes=missing_attributes(row),
        variants=[to_listing(variant) for variant in row.variants],
    )


def tokens(text: str) -> List[str]:
    return [token.casefold() for token in _TOKEN.findall(text or "") if len(token) > 1 or not token.isascii()]


def score(row: CatalogProduct, words: Iterable[str]) -> int:
    haystack = " ".join(
        [
            row.id,
            row.title or "",
            row.brand or "",
            row.category or "",
            row.short_description or "",
            row.long_description or "",
            " ".join(f"{k} {v}" for k, v in (row.attributes_json or {}).items()),
        ]
    ).casefold()
    total = 0
    for word in words:
        if word == row.id.casefold():
            total += 20
        elif word in (row.title or "").casefold():
            total += 5
        elif word in haystack:
            total += 2
    return total


def families(db: Session, statuses: Iterable[str]) -> List[CatalogProduct]:
    """Top-level records (plain products and families) in the given statuses."""
    return (
        db.query(CatalogProduct)
        .filter(CatalogProduct.parent_id.is_(None), CatalogProduct.status.in_(list(statuses)))
        .order_by(CatalogProduct.id)
        .limit(2000)
        .all()
    )


def ranked(rows: List[CatalogProduct], query: str) -> List[CatalogProduct]:
    words = tokens(query)
    if not words:
        return rows
    scored = [(score(row, words), row) for row in rows]
    return [row for value, row in sorted(scored, key=lambda pair: -pair[0]) if value > 0]
