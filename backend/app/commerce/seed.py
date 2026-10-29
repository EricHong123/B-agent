"""A fictional export catalog, versioned trade terms and campaigns for demos and tests.

Every product, brand and figure here is invented. Seeding is idempotent: records that
already exist are left as they are.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.database import CatalogProduct, MarketingCampaign, TradeTerm


def _product(**fields: Any) -> Dict[str, Any]:
    return fields


PRODUCTS: List[Dict[str, Any]] = [
    _product(
        id="BTL-5001",
        title="Double-wall vacuum bottle 500 ml",
        brand="Northgate",
        category="drinkware",
        short_description="18/8 stainless steel, 12 h hot / 24 h cold, powder-coated, laser-engraving ready.",
        long_description=(
            "Double-wall vacuum bottle with a leak-proof bamboo lid. Food-grade 18/8 stainless "
            "steel inner wall, powder-coated outer wall in four colours. Custom logo by laser "
            "engraving or screen print from 500 units."
        ),
        attributes={
            "material": "18/8 stainless steel",
            "origin": "China",
            "hs_code": "9617.00",
            "certifications": "LFGB, FDA",
            "packaging": "white box, 25 pcs per carton",
            "port_of_loading": "Ningbo",
            "unit": "pcs",
        },
        specs={"capacity": "500 ml", "weight": "320 g", "carton": "52 x 32 x 28 cm"},
        options={"color": ["Black", "White", "Sage"]},
        price="4.80",
        unit_cost="3.25",
        moq=500,
        lead_time_days=30,
        variants=[
            {"id": "BTL-5001-BLK", "option_values": {"color": "Black"}, "price": "4.80", "unit_cost": "3.25", "stock": 1800, "reorder_point": 1000, "sales_last_30d": 2400},
            {"id": "BTL-5001-WHT", "option_values": {"color": "White"}, "price": "4.80", "unit_cost": "3.25", "stock": 650, "reorder_point": 1000, "sales_last_30d": 1900},
            {"id": "BTL-5001-SGE", "option_values": {"color": "Sage"}, "price": "4.95", "unit_cost": "3.40", "stock": 4200, "reorder_point": 800, "sales_last_30d": 0},
        ],
    ),
    _product(
        id="MUG-2204",
        title="Ceramic stoneware mug 350 ml",
        brand="Northgate",
        category="drinkware",
        short_description="Reactive-glaze stoneware mug, dishwasher and microwave safe.",
        long_description="Stoneware mug with a reactive glaze. Each piece varies slightly in tone.",
        attributes={"material": "stoneware", "origin": "China", "hs_code": "6912.00", "port_of_loading": "Xiamen", "unit": "pcs"},
        specs={"capacity": "350 ml"},
        price="1.95",
        unit_cost="1.20",
        moq=1000,
        lead_time_days=35,
        stock=8000,
        reorder_point=2000,
        sales_last_30d=3100,
    ),
    _product(
        id="LED-3108",
        title="LED panel light 600 x 600 mm 40 W",
        brand="Lumora",
        category="lighting",
        short_description="Back-lit LED panel, 110 lm/W, flicker-free driver, 5-year warranty.",
        long_description=(
            "Back-lit LED panel for suspended ceilings. Isolated flicker-free driver, UGR<19, "
            "CRI>80. Colour temperature selectable at order."
        ),
        attributes={
            "material": "aluminium frame, PS diffuser",
            "origin": "China",
            "hs_code": "9405.11",
            "certifications": "CE, RoHS",
            "packaging": "2 pcs per carton",
            "port_of_loading": "Shenzhen",
            "unit": "pcs",
        },
        specs={"power": "40 W", "flux": "4400 lm", "voltage": "AC 100-240 V"},
        price="11.40",
        unit_cost="8.60",
        min_price="9.90",
        moq=200,
        lead_time_days=25,
        stock=320,
        reorder_point=400,
        sales_last_30d=900,
    ),
    _product(
        id="BAG-7012",
        title="Recycled PET tote bag",
        brand="Fieldline",
        category="bags",
        short_description="Laminated rPET tote with gusset, custom full-colour print.",
        long_description="Tote bag woven from recycled PET with a laminated finish for full-colour prints.",
        attributes={"material": "rPET 120 gsm", "origin": "Vietnam", "hs_code": "4202.92", "packaging": "100 pcs per carton", "port_of_loading": "Ho Chi Minh City", "unit": "pcs"},
        price="0.86",
        unit_cost="0.52",
        moq=3000,
        lead_time_days=28,
        stock=0,
        reorder_point=5000,
        sales_last_30d=12000,
    ),
    _product(
        id="KIT-4410",
        title="Silicone kitchen utensil set, 6 pieces",
        brand="Hearthly",
        category="kitchenware",
        short_description="Heat-resistant to 230 °C, beech handles, hanging holes.",
        long_description="Six-piece utensil set in platinum-cured silicone with beech wood handles.",
        attributes={"material": "silicone, beech", "origin": "China", "hs_code": "3924.10", "certifications": "LFGB", "packaging": "colour box, 24 sets per carton", "port_of_loading": "Ningbo", "unit": "sets"},
        price="6.20",
        unit_cost="4.10",
        moq=300,
        lead_time_days=40,
        stock=1500,
        reorder_point=300,
        sales_last_30d=0,
        status="active",
    ),
]

TERMS: List[Dict[str, Any]] = [
    {
        "id": "terms/payment@1",
        "source_id": "terms/payment",
        "version": "1",
        "title": "Payment terms",
        "category": "payment",
        "content": "40% T/T deposit with the order and 60% balance against copy of the bill of lading.",
        "effective_at": datetime(2025, 1, 1),
        "expires_at": datetime(2026, 1, 1),
    },
    {
        "id": "terms/payment@2",
        "source_id": "terms/payment",
        "version": "2",
        "title": "Payment terms",
        "category": "payment",
        "content": (
            "30% T/T deposit with the order and 70% balance before shipment. Irrevocable L/C at "
            "sight is accepted for orders above USD 30,000. Production starts when the deposit "
            "is received."
        ),
        "effective_at": datetime(2026, 1, 1),
        "expires_at": None,
    },
    {
        "id": "terms/samples@1",
        "source_id": "terms/samples",
        "version": "1",
        "title": "Samples and minimum order quantity",
        "category": "samples",
        "content": (
            "Up to three stock samples are free; the buyer pays air express. Custom-logo samples "
            "cost USD 50 per design, refunded on orders at or above the MOQ. Orders below the "
            "MOQ are quoted case by case with a small-batch surcharge."
        ),
        "effective_at": datetime(2025, 6, 1),
        "expires_at": None,
    },
    {
        "id": "terms/quality@1",
        "source_id": "terms/quality",
        "version": "1",
        "title": "Quality inspection and claims",
        "category": "quality",
        "content": (
            "Every order passes a pre-shipment inspection to AQL 2.5. Third-party inspection is "
            "welcome at the buyer's cost. Claims for defects must reach us within 30 days of "
            "arrival with photos; confirmed defects are replaced in the next shipment or credited."
        ),
        "effective_at": datetime(2025, 6, 1),
        "expires_at": None,
    },
    {
        "id": "terms/shipping@1",
        "source_id": "terms/shipping",
        "version": "1",
        "title": "Shipping and Incoterms",
        "category": "shipping",
        "content": (
            "Prices are FOB the named port of loading unless the quotation states otherwise. "
            "CIF and DDP quotations are available on request. Lead time counts from deposit and "
            "artwork approval."
        ),
        "effective_at": datetime(2025, 6, 1),
        "expires_at": None,
    },
]


def seed_demo_catalog(db: Session) -> Dict[str, int]:
    created = {"products": 0, "terms": 0, "campaigns": 0}
    for spec in PRODUCTS:
        spec = dict(spec)
        variants = spec.pop("variants", [])
        if db.get(CatalogProduct, spec["id"]) is not None:
            continue
        parent = CatalogProduct(
            id=spec["id"],
            title=spec["title"],
            brand=spec.get("brand"),
            category=spec.get("category"),
            status=spec.get("status", "active"),
            short_description=spec.get("short_description"),
            long_description=spec.get("long_description"),
            attributes_json=spec.get("attributes", {}),
            specs_json=spec.get("specs", {}),
            options_json=spec.get("options", {}),
            option_values_json={},
            labels_json=[],
            price=Decimal(spec["price"]),
            currency="USD",
            unit_cost=Decimal(spec["unit_cost"]) if spec.get("unit_cost") else None,
            min_price=Decimal(spec["min_price"]) if spec.get("min_price") else None,
            moq=spec.get("moq", 1),
            lead_time_days=spec.get("lead_time_days"),
            stock=spec.get("stock", 0),
            reorder_point=spec.get("reorder_point", 0),
            sales_last_30d=spec.get("sales_last_30d", 0),
        )
        db.add(parent)
        created["products"] += 1
        for variant in variants:
            colour = next(iter(variant["option_values"].values()))
            db.add(
                CatalogProduct(
                    id=variant["id"],
                    parent_id=spec["id"],
                    title=f"{spec['title']} · {colour}",
                    category=spec.get("category"),
                    status="active",
                    attributes_json={},
                    specs_json={},
                    options_json={},
                    option_values_json=variant["option_values"],
                    labels_json=[],
                    price=Decimal(variant["price"]),
                    currency="USD",
                    unit_cost=Decimal(variant["unit_cost"]),
                    moq=spec.get("moq", 1),
                    lead_time_days=spec.get("lead_time_days"),
                    stock=variant["stock"],
                    reorder_point=variant["reorder_point"],
                    sales_last_30d=variant["sales_last_30d"],
                )
            )
            created["products"] += 1
    for term in TERMS:
        if db.get(TradeTerm, term["id"]) is None:
            db.add(TradeTerm(**term))
            created["terms"] += 1
    today = date.today()
    campaigns = [
        MarketingCampaign(
            id="cmp-trade-fair",
            name="Autumn trade fair follow-up",
            status="active",
            objective="Convert fair contacts into sample orders",
            channel="email",
            budget=Decimal("3000"),
            spend=Decimal("1240"),
            revenue=Decimal("18600"),
            starts=today - timedelta(days=20),
            ends=today + timedelta(days=10),
        ),
        MarketingCampaign(
            id="cmp-eu-drinkware",
            name="EU drinkware launch",
            status="draft",
            objective="Introduce the vacuum bottle line to EU importers",
            channel="linkedin",
            budget=Decimal("5000"),
            starts=today + timedelta(days=14),
            ends=today + timedelta(days=60),
        ),
    ]
    for campaign in campaigns:
        if db.get(MarketingCampaign, campaign.id) is None:
            db.add(campaign)
            created["campaigns"] += 1
    db.commit()
    return created
