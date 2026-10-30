"""Add the commerce agents: catalog, trade terms, campaigns, sessions and change ledger.

Revision ID: 0033_commerce_agents
Revises: 0032_fulfillment_pipeline
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0033_commerce_agents"
down_revision: Union[str, None] = "0032_fulfillment_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("catalog_products",
    sa.Column("id", sa.String(length=80), nullable=False),
    sa.Column("parent_id", sa.String(length=80), nullable=True),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("brand", sa.String(length=100), nullable=True),
    sa.Column("category", sa.String(length=100), nullable=True),
    sa.Column("status", sa.String(length=20), nullable=False),
    sa.Column("short_description", sa.String(length=500), nullable=True),
    sa.Column("long_description", sa.Text(), nullable=True),
    sa.Column("attributes_json", sa.JSON(), nullable=False),
    sa.Column("specs_json", sa.JSON(), nullable=False),
    sa.Column("options_json", sa.JSON(), nullable=False),
    sa.Column("option_values_json", sa.JSON(), nullable=False),
    sa.Column("labels_json", sa.JSON(), nullable=False),
    sa.Column("price", sa.Numeric(precision=14, scale=4), nullable=False),
    sa.Column("currency", sa.String(length=3), nullable=False),
    sa.Column("unit_cost", sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column("min_price", sa.Numeric(precision=14, scale=4), nullable=True),
    sa.Column("moq", sa.Integer(), nullable=False),
    sa.Column("lead_time_days", sa.Integer(), nullable=True),
    sa.Column("stock", sa.Integer(), nullable=False),
    sa.Column("reorder_point", sa.Integer(), nullable=False),
    sa.Column("sales_last_30d", sa.Integer(), nullable=False),
    sa.Column("image_url", sa.String(length=1000), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.CheckConstraint("moq >= 1", name="ck_catalog_product_moq"),
    sa.CheckConstraint("price >= 0", name="ck_catalog_product_price"),
    sa.ForeignKeyConstraint(["parent_id"], ["catalog_products.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_index("idx_catalog_product_parent", "catalog_products", ["parent_id"], unique=False)
    op.create_index("idx_catalog_product_status_category", "catalog_products", ["status", "category"], unique=False)
    op.create_index(op.f("ix_catalog_products_category"), "catalog_products", ["category"], unique=False)
    op.create_table("catalog_promotions",
    sa.Column("id", sa.String(length=40), nullable=False),
    sa.Column("name", sa.String(length=80), nullable=False),
    sa.Column("listing_ids_json", sa.JSON(), nullable=False),
    sa.Column("discount_pct", sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column("starts", sa.Date(), nullable=False),
    sa.Column("ends", sa.Date(), nullable=False),
    sa.Column("status", sa.String(length=20), nullable=False),
    sa.Column("change_id", sa.String(length=40), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("commerce_memory_facts",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("subject_id", sa.String(length=80), nullable=False),
    sa.Column("key", sa.String(length=64), nullable=False),
    sa.Column("value", sa.String(length=200), nullable=False),
    sa.Column("category", sa.String(length=20), nullable=False),
    sa.Column("source_session_id", sa.String(length=80), nullable=True),
    sa.Column("updated_at", sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("subject_id", "key", name="uq_commerce_memory_subject_key")
    )
    op.create_table("commerce_memory_purges",
    sa.Column("subject_id", sa.String(length=80), nullable=False),
    sa.Column("generation", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("subject_id")
    )
    op.create_table("marketing_campaigns",
    sa.Column("id", sa.String(length=40), nullable=False),
    sa.Column("name", sa.String(length=80), nullable=False),
    sa.Column("status", sa.String(length=20), nullable=False),
    sa.Column("objective", sa.String(length=200), nullable=True),
    sa.Column("channel", sa.String(length=50), nullable=True),
    sa.Column("audience", sa.String(length=300), nullable=True),
    sa.Column("copy_text", sa.String(length=600), nullable=True),
    sa.Column("budget", sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column("spend", sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column("revenue", sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column("currency", sa.String(length=3), nullable=False),
    sa.Column("starts", sa.Date(), nullable=True),
    sa.Column("ends", sa.Date(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("trade_terms",
    sa.Column("id", sa.String(length=80), nullable=False),
    sa.Column("source_id", sa.String(length=80), nullable=False),
    sa.Column("version", sa.String(length=20), nullable=False),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("category", sa.String(length=50), nullable=True),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("effective_at", sa.DateTime(), nullable=False),
    sa.Column("expires_at", sa.DateTime(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("source_id", "version", name="uq_trade_term_source_version")
    )
    op.create_index("idx_trade_term_source", "trade_terms", ["source_id", "effective_at"], unique=False)
    op.create_table("buyer_portal_invites",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("customer_id", sa.Integer(), nullable=False),
    sa.Column("created_by_user_id", sa.Integer(), nullable=False),
    sa.Column("token_hash", sa.String(length=64), nullable=False),
    sa.Column("expires_at", sa.DateTime(), nullable=False),
    sa.Column("revoked_at", sa.DateTime(), nullable=True),
    sa.Column("last_used_at", sa.DateTime(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ),
    sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("token_hash")
    )
    op.create_index("idx_buyer_portal_invite_customer", "buyer_portal_invites", ["customer_id", "created_at"], unique=False)
    op.create_table("commerce_cart_lines",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("customer_id", sa.Integer(), nullable=False),
    sa.Column("product_id", sa.String(length=80), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.CheckConstraint("quantity >= 1", name="ck_commerce_cart_quantity"),
    sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("customer_id", "product_id", name="uq_commerce_cart_line")
    )
    op.create_table("commerce_operation_events",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("role", sa.String(length=20), nullable=False),
    sa.Column("kind", sa.String(length=20), nullable=False),
    sa.Column("session_id", sa.String(length=64), nullable=True),
    sa.Column("turn_id", sa.String(length=40), nullable=True),
    sa.Column("ticket", sa.String(length=20), nullable=True),
    sa.Column("record_json", sa.JSON(), nullable=False),
    sa.Column("resolved_at", sa.DateTime(), nullable=True),
    sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_index("idx_commerce_operation_kind", "commerce_operation_events", ["role", "kind", "created_at"], unique=False)
    op.create_index("idx_commerce_operation_session", "commerce_operation_events", ["session_id", "created_at"], unique=False)
    op.create_index("idx_commerce_operation_turn", "commerce_operation_events", ["turn_id"], unique=False)
    op.create_table("commerce_staged_changes",
    sa.Column("id", sa.String(length=40), nullable=False),
    sa.Column("kind", sa.String(length=30), nullable=False),
    sa.Column("status", sa.String(length=20), nullable=False),
    sa.Column("document_json", sa.JSON(), nullable=False),
    sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_index("idx_commerce_staged_change_status", "commerce_staged_changes", ["status", "created_at"], unique=False)
    op.create_table("commerce_sessions",
    sa.Column("id", sa.String(length=64), nullable=False),
    sa.Column("role", sa.String(length=20), nullable=False),
    sa.Column("subject_id", sa.String(length=80), nullable=False),
    sa.Column("user_id", sa.Integer(), nullable=True),
    sa.Column("customer_id", sa.Integer(), nullable=True),
    sa.Column("invite_id", sa.Uuid(), nullable=True),
    sa.Column("state_json", sa.JSON(), nullable=False),
    sa.Column("pending_app_events_json", sa.JSON(), nullable=False),
    sa.Column("messages_json", sa.JSON(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["invite_id"], ["buyer_portal_invites.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_index("idx_commerce_session_subject", "commerce_sessions", ["role", "subject_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_commerce_session_subject", table_name="commerce_sessions")
    op.drop_table("commerce_sessions")
    op.drop_index("idx_commerce_staged_change_status", table_name="commerce_staged_changes")
    op.drop_table("commerce_staged_changes")
    op.drop_index("idx_commerce_operation_turn", table_name="commerce_operation_events")
    op.drop_index("idx_commerce_operation_session", table_name="commerce_operation_events")
    op.drop_index("idx_commerce_operation_kind", table_name="commerce_operation_events")
    op.drop_table("commerce_operation_events")
    op.drop_table("commerce_cart_lines")
    op.drop_index("idx_buyer_portal_invite_customer", table_name="buyer_portal_invites")
    op.drop_table("buyer_portal_invites")
    op.drop_index("idx_trade_term_source", table_name="trade_terms")
    op.drop_table("trade_terms")
    op.drop_table("marketing_campaigns")
    op.drop_table("commerce_memory_purges")
    op.drop_table("commerce_memory_facts")
    op.drop_table("catalog_promotions")
    op.drop_index(op.f("ix_catalog_products_category"), table_name="catalog_products")
    op.drop_index("idx_catalog_product_status_category", table_name="catalog_products")
    op.drop_index("idx_catalog_product_parent", table_name="catalog_products")
    op.drop_table("catalog_products")
