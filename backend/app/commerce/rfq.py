"""The buyer basket's checkout: a request for quotation in the fulfillment pipeline.

Submitting creates a qualified opportunity sourced from the buyer assistant and a draft
quotation at list prices for the sales rep who owns the buyer's access. Nothing is sent
or approved here: the draft follows the normal submit, review and send gates.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.database import CatalogProduct, CommerceCartLine, Customer, SalesOpportunity, User
from app.services.fulfillment import (
    FulfillmentConflict,
    FulfillmentService,
    OpportunityCreate,
    OpportunityRequirements,
    OpportunityTransition,
    QuotationCreate,
    QuotationLineItem,
)


@dataclass
class RfqResult:
    opportunity_id: str
    quotation_id: str
    quote_number: str
    below_moq: List[str]


def submit_rfq(
    db: Session,
    *,
    customer_id: int,
    owner: User,
    note: Optional[str] = None,
    destination: Optional[str] = None,
) -> RfqResult:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise FulfillmentConflict("Customer not found")
    lines = (
        db.query(CommerceCartLine)
        .filter(CommerceCartLine.customer_id == customer_id)
        .order_by(CommerceCartLine.id)
        .all()
    )
    products = [(line, db.get(CatalogProduct, line.product_id)) for line in lines]
    products = [(line, product) for line, product in products if product is not None]
    if not products:
        raise FulfillmentConflict("The RFQ basket is empty")
    currencies = {product.currency for _, product in products}
    if len(currencies) > 1:
        raise FulfillmentConflict("An RFQ is quoted in one currency")

    below_moq = [product.id for line, product in products if line.quantity < product.moq]
    total_units = sum(line.quantity for line, _ in products)
    first = products[0][1]
    service = FulfillmentService(db)
    summary_lines = [f"{line.quantity} × {product.title} ({product.id})" for line, product in products]
    if below_moq:
        summary_lines.append("Below MOQ: " + ", ".join(below_moq))
    if note:
        summary_lines.append(f"Buyer note: {note.strip()[:1000]}")

    opportunity = service.create_opportunity(
        OpportunityCreate(
            customer_id=customer.id,
            title=f"RFQ · {customer.company_name or customer.username or customer.id} · {len(products)} item(s)",
            inquiry_summary="\n".join(summary_lines),
            requirements=OpportunityRequirements(
                product=first.title[:255],
                quantity=Decimal(total_units),
                unit=(first.attributes_json or {}).get("unit", "pcs"),
                destination_country=destination or customer.country,
            ),
            currency=next(iter(currencies)),
        ),
        actor=owner,
    )
    row = db.get(SalesOpportunity, opportunity.id)
    row.source = "buyer_assistant"
    db.commit()
    service.transition_opportunity(opportunity.id, OpportunityTransition(stage="qualified"), actor=owner)
    quotation = service.create_quotation(
        opportunity.id,
        QuotationCreate(
            currency=next(iter(currencies)),
            incoterm="FOB",
            lead_time_days=max((product.lead_time_days or 30) for _, product in products),
            line_items=[
                QuotationLineItem(
                    product=product.title[:255],
                    sku=product.id,
                    description=(product.short_description or "")[:1000] or None,
                    hs_code=(product.attributes_json or {}).get("hs_code") or None,
                    quantity=Decimal(line.quantity),
                    unit=(product.attributes_json or {}).get("unit", "pcs"),
                    unit_price=Decimal(product.price).quantize(Decimal("0.0001")),
                    unit_cost=(
                        Decimal(product.unit_cost).quantize(Decimal("0.0001"))
                        if product.unit_cost is not None
                        else None
                    ),
                )
                for line, product in products
            ],
            notes="Drafted from the buyer assistant's RFQ basket at list prices; review before submitting.",
        ),
        actor=owner,
    )
    db.query(CommerceCartLine).filter(CommerceCartLine.customer_id == customer_id).delete()
    db.commit()
    return RfqResult(
        opportunity_id=str(opportunity.id),
        quotation_id=str(quotation.id),
        quote_number=quotation.quote_number,
        below_moq=below_moq,
    )
