"""The B-agent vertical for the vendored evaluations (``commerce/scripts/eval_go_live.py``
and ``eval_constraints.py``): the real buyer backend over an in-memory database seeded
with the demo catalog and trade terms. ``_policies`` holds the passages the harness
judges against and may extend with a case's overlay records."""

from contextlib import contextmanager
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shopping_agent import Policy, ProductDetails, ShoppingSessionContext

from app.commerce.catalog import SELLABLE_STATUSES, families, to_details
from app.commerce.seed import TERMS, seed_demo_catalog
from app.commerce.storefront import BAgentStorefront, rank_policies
from app.db import Base
from app.models.database import CatalogProduct, Customer


class EvalStorefront(BAgentStorefront):
    def __init__(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()
        seed_demo_catalog(db)
        customer = Customer(username="eval-buyer", platform="email", company_name="Evaluation Imports")
        db.add(customer)
        db.commit()
        self._eval_customer_id = customer.id

        @contextmanager
        def scope():
            yield db

        super().__init__(scope)
        self._policies: List[Policy] = [
            Policy(
                policy_id=term["id"],
                title=term["title"],
                category=term["category"],
                content=term["content"],
                source_id=term["source_id"],
                version=term["version"],
                effective_at=term["effective_at"],
                expires_at=term["expires_at"],
            )
            for term in TERMS
        ]

        self._db = db

    @property
    def products(self) -> List[str]:
        """Top-level catalog ids, as the constraint harness walks them."""
        return [row.id for row in families(self._db, SELLABLE_STATUSES)]

    def product(self, product_id: str) -> Optional[ProductDetails]:
        row = self._db.get(CatalogProduct, product_id)
        return to_details(row) if row is not None else None

    def _customer_id(self, session: ShoppingSessionContext) -> int:
        return self._eval_customer_id

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> List[Policy]:
        return rank_policies(self._policies, query)
