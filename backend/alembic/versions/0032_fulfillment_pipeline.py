"""Add the opportunity-to-delivery fulfillment pipeline.

Revision ID: 0032_fulfillment_pipeline
Revises: 0031_media_pricing_snapshots
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0032_fulfillment_pipeline"
down_revision: Union[str, None] = "0031_media_pricing_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("inquiry_summary", sa.Text(), nullable=True),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("estimated_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("won_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sales_opportunity_user_stage",
        "sales_opportunities",
        ["user_id", "stage", "updated_at"],
    )
    op.create_index(
        "idx_sales_opportunity_customer",
        "sales_opportunities",
        ["customer_id"],
    )

    op.create_table(
        "sales_quotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quote_number", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incoterm", sa.String(length=10), nullable=False),
        sa.Column("payment_terms", sa.String(length=255), nullable=False),
        sa.Column("deposit_percent", sa.Integer(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("line_items_json", sa.JSON(), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("freight_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("margin_percent", sa.Numeric(7, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("sent_channel", sa.String(length=30), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "deposit_percent >= 0 AND deposit_percent <= 100",
            name="ck_sales_quotation_deposit_percent",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["sales_opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_number"),
        sa.UniqueConstraint(
            "opportunity_id",
            "revision",
            name="uq_sales_quotation_revision",
        ),
    )
    op.create_index(
        "idx_sales_quotation_status",
        "sales_quotations",
        ["status", "valid_until"],
    )

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("customer_po_number", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("fulfillment_mode", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("incoterm", sa.String(length=10), nullable=False),
        sa.Column("payment_terms", sa.String(length=255), nullable=False),
        sa.Column("line_items_json", sa.JSON(), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("deposit_required", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_before_shipment", sa.Boolean(), nullable=False),
        sa.Column("required_ship_date", sa.Date(), nullable=True),
        sa.Column("shipping_address", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("production_started_at", sa.DateTime(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["sales_opportunities.id"]),
        sa.ForeignKeyConstraint(["quotation_id"], ["sales_quotations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
        sa.UniqueConstraint("quotation_id"),
    )
    op.create_index(
        "idx_sales_order_user_status",
        "sales_orders",
        ["user_id", "status", "updated_at"],
    )
    op.create_index(
        "idx_sales_order_ship_date",
        "sales_orders",
        ["status", "required_ship_date"],
    )

    op.create_table(
        "production_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("reference_number", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("production_line", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_finish", sa.Date(), nullable=True),
        sa.Column("actual_start", sa.DateTime(), nullable=True),
        sa.Column("actual_finish", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_production_task_progress",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_number"),
    )
    op.create_index(
        "idx_production_task_order_status",
        "production_tasks",
        ["order_id", "status"],
    )
    op.create_index(
        "idx_production_task_finish",
        "production_tasks",
        ["status", "planned_finish"],
    )

    op.create_table(
        "quality_inspections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("production_task_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("inspector", sa.String(length=255), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("defects_json", sa.JSON(), nullable=False),
        sa.Column("report_url", sa.String(length=1000), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("inspected_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["production_task_id"], ["production_tasks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_quality_inspection_order",
        "quality_inspections",
        ["order_id", "stage", "inspected_at"],
    )

    op.create_table(
        "order_shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("shipment_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("transport_mode", sa.String(length=20), nullable=False),
        sa.Column("carrier", sa.String(length=255), nullable=False),
        sa.Column("tracking_number", sa.String(length=255), nullable=True),
        sa.Column("bill_of_lading", sa.String(length=255), nullable=True),
        sa.Column("container_number", sa.String(length=100), nullable=True),
        sa.Column("port_of_loading", sa.String(length=255), nullable=True),
        sa.Column("port_of_discharge", sa.String(length=255), nullable=True),
        sa.Column("etd", sa.Date(), nullable=True),
        sa.Column("eta", sa.Date(), nullable=True),
        sa.Column("departed_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shipment_number"),
    )
    op.create_index(
        "idx_order_shipment_order_status",
        "order_shipments",
        ["order_id", "status"],
    )

    op.create_table(
        "order_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_order_payment_amount_positive"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "idempotency_key",
            name="uq_order_payment_idempotency",
        ),
    )

    op.create_table(
        "fulfillment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["sales_opportunities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_fulfillment_event_opportunity",
        "fulfillment_events",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "idx_fulfillment_event_order",
        "fulfillment_events",
        ["order_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("fulfillment_events")
    op.drop_table("order_payments")
    op.drop_table("order_shipments")
    op.drop_table("quality_inspections")
    op.drop_table("production_tasks")
    op.drop_table("sales_orders")
    op.drop_table("sales_quotations")
    op.drop_table("sales_opportunities")
