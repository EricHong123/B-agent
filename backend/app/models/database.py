"""
SQLAlchemy database models
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    BigInteger, Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey, Enum,
    JSON, Float, Numeric, Index, UniqueConstraint, CheckConstraint, text
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from app.db import Base


class WorkflowStatus(str, enum.Enum):
    """Workflow status enum"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ExecutionStatus(str, enum.Enum):
    """Execution status enum"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutreachStatus(str, enum.Enum):
    """Outreach status enum"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    REPLIED = "replied"
    FAILED = "failed"
    BOUNCED = "bounced"


class ConversationStatus(str, enum.Enum):
    """Conversation status enum"""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


class TaskStatus(str, enum.Enum):
    """Task status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class IntentLevel(str, enum.Enum):
    """Intent level enum"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class LLMInvocationStatus(str, enum.Enum):
    """Durable lifecycle of one business-level LLM invocation."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class LLMAttemptStatus(str, enum.Enum):
    """Outcome of one provider/gateway attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class OutboxStatus(str, enum.Enum):
    """Durable delivery state for an external side effect."""

    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    SENT = "sent"
    DEAD_LETTER = "dead_letter"


class OutboxResolutionAction(str, enum.Enum):
    """Evidence-backed operator conclusion for a dead-letter event."""

    CONFIRMED_NOT_SENT = "confirmed_not_sent"
    CONFIRMED_SENT = "confirmed_sent"


class OutboxResolutionStatus(str, enum.Enum):
    """Lifecycle of a two-person dead-letter resolution request."""

    PENDING = "pending"
    EXECUTED = "executed"


class MediaSubmissionResolutionAction(str, enum.Enum):
    """Evidence-backed conclusion for an ambiguous provider submission."""

    CONFIRMED_SUBMITTED = "confirmed_submitted"
    CONFIRMED_NOT_SUBMITTED = "confirmed_not_submitted"


class MediaSubmissionResolutionStatus(str, enum.Enum):
    """Lifecycle of a two-person media submission resolution."""

    PENDING = "pending"
    EXECUTED = "executed"


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default="user")  # admin, user, operator
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    workflows = relationship("Workflow", back_populates="user", cascade="all, delete-orphan")


class Workflow(Base):
    """Workflow model"""
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.DRAFT)
    config_json = Column(JSON)
    variables = Column(JSON, default={})
    user_id = Column(Integer, ForeignKey("users.id"))
    version = Column(String(20), default="1.0.0")
    tags = Column(JSON, default=[])  # List of tag strings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="workflows")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_workflow_user_status', 'user_id', 'status'),
    )


class WorkflowExecution(Base):
    """Workflow execution model"""
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"))
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.PENDING)
    current_step = Column(String(100))
    context_json = Column(JSON)
    error_msg = Column(Text)
    error_stack = Column(Text)
    input_data = Column(JSON)
    output_data = Column(JSON)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    completed_steps = Column(JSON, default=[])  # List of step names
    failed_steps = Column(JSON, default=[])  # List of step names
    paused_steps = Column(JSON, default=[])  # List of step names
    metrics = Column(JSON, default={})  # Execution metrics

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")

    __table_args__ = (
        Index('idx_execution_workflow_status', 'workflow_id', 'status'),
        Index('idx_execution_started_at', 'started_at'),
    )


class Customer(Base):
    """Customer model"""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100))
    platform = Column(String(50))  # tiktok, instagram, facebook, youtube, etc.
    email = Column(String(255), index=True)
    whatsapp = Column(String(20))
    phone = Column(String(20))
    country = Column(String(10), index=True)
    category = Column(String(50))  # fashion, beauty, electronics, etc.
    subcategory = Column(String(50))
    follower_count = Column(Integer)
    account_type = Column(String(20))  # creator, brand, mcn, retailer
    intent_level = Column(Enum(IntentLevel))
    tags_json = Column(JSON, default=[])  # List of tags
    source_data_json = Column(JSON)  # Raw data from source
    contact_info = Column(JSON)  # Additional contact info
    social_links = Column(JSON)  # Links to social profiles
    website = Column(String(255))
    company_name = Column(String(100))
    job_title = Column(String(100))

    # Status tracking
    status = Column(String(20), default="new")  # new, contacted, engaged, converted, lost
    first_contacted_at = Column(DateTime)
    last_contacted_at = Column(DateTime)
    last_replied_at = Column(DateTime)

    # Metadata
    notes = Column(Text)
    custom_fields = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    outreach_logs = relationship("OutreachLog", back_populates="customer", cascade="all, delete-orphan")
    contact_verifications = relationship(
        "ContactVerification",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    research_jobs = relationship(
        "AgentResearchJob",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index('idx_customer_platform_status', 'platform', 'status'),
        Index('idx_customer_country_category', 'country', 'category'),
        UniqueConstraint('username', 'platform', name='uq_customer_username_platform'),
    )


class ConnectorConfiguration(Base):
    """Versioned connector metadata; provider secrets live outside the database."""

    __tablename__ = "connector_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    config_json = Column(JSON, nullable=False, default=dict)
    secret_ref = Column(String(500), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    last_status = Column(String(30), nullable=False, default="not_tested")
    last_error_code = Column(String(100))
    last_tested_at = Column(DateTime)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("provider", "name", name="uq_connector_provider_name"),
        Index("idx_connector_provider_enabled", "provider", "enabled"),
    )


class ContactVerification(Base):
    """Auditable outcome of one contact verification request."""

    __tablename__ = "contact_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    email = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    score = Column(Integer)
    retryable = Column(Boolean, nullable=False, default=False)
    legal_restricted = Column(Boolean, nullable=False, default=False)
    details_json = Column(JSON, nullable=False, default=dict)
    verified_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="contact_verifications")

    __table_args__ = (
        Index(
            "idx_contact_verification_customer_verified",
            "customer_id",
            "verified_at",
        ),
        Index("idx_contact_verification_email_status", "email", "status"),
    )


class ProspectingSearch(Base):
    """Durable search record without storing named-person query PII."""

    __tablename__ = "prospecting_searches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(50), nullable=False, default="hunter")
    mode = Column(String(30), nullable=False)
    query_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(30), nullable=False, default="running")
    connector_version = Column(Integer, nullable=False, default=0)
    result_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(100))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)

    contacts = relationship(
        "ProspectingContact",
        back_populates="search",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_prospecting_search_user_created", "user_id", "created_at"),
        Index("idx_prospecting_search_status_created", "status", "created_at"),
    )


class ProspectingContact(Base):
    """Normalized, evidence-backed contact candidate from a search."""

    __tablename__ = "prospecting_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    search_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_searches.id", ondelete="CASCADE"),
        nullable=False,
    )
    email = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    company = Column(String(255))
    domain = Column(String(255))
    position = Column(String(255))
    department = Column(String(50))
    seniority = Column(String(50))
    contact_type = Column(String(30))
    confidence = Column(Integer)
    decision_maker = Column(Boolean)
    verification_status = Column(String(30), nullable=False, default="unknown")
    verification_date = Column(String(20))
    evidence_json = Column(JSON, nullable=False, default=list)
    imported_customer_id = Column(Integer, ForeignKey("customers.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    search = relationship("ProspectingSearch", back_populates="contacts")
    icp_score = relationship(
        "ProspectingContactScore",
        back_populates="contact",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("search_id", "email", name="uq_prospecting_search_email"),
        Index("idx_prospecting_contact_search", "search_id"),
        Index("idx_prospecting_contact_email", "email"),
        Index("idx_prospecting_contact_imported", "imported_customer_id"),
    )


class ProspectingIcpProfile(Base):
    """Versioned, user-owned and deterministic prospect qualification policy."""

    __tablename__ = "prospecting_icp_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    target_departments_json = Column(JSON, nullable=False, default=list)
    target_seniorities_json = Column(JSON, nullable=False, default=list)
    title_keywords_json = Column(JSON, nullable=False, default=list)
    preferred_contact_types_json = Column(JSON, nullable=False, default=list)
    weights_json = Column(JSON, nullable=False, default=dict)
    minimum_score = Column(Integer, nullable=False, default=65)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class ProspectingContactScore(Base):
    """Explainable ICP score with a separately preserved human review."""

    __tablename__ = "prospecting_contact_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_contacts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_icp_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_version = Column(Integer, nullable=False)
    base_score = Column(Float, nullable=False)
    factor_scores_json = Column(JSON, nullable=False, default=dict)
    reasons_json = Column(JSON, nullable=False, default=list)
    missing_signals_json = Column(JSON, nullable=False, default=list)
    review_status = Column(String(30), nullable=False, default="unreviewed")
    review_reason = Column(Text)
    score_adjustment = Column(Integer, nullable=False, default=0)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    scored_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    contact = relationship("ProspectingContact", back_populates="icp_score")
    profile = relationship("ProspectingIcpProfile")

    __table_args__ = (
        Index("idx_prospecting_score_profile_score", "profile_id", "base_score"),
        Index("idx_prospecting_score_review", "review_status", "reviewed_at"),
    )


class AgentResearchJob(Base):
    """Versioned, user-owned dossier built from explicitly sourced evidence."""

    __tablename__ = "agent_research_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    objective = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    profile_evidence_json = Column(JSON, nullable=False, default=list)
    market_signals_json = Column(JSON, nullable=False, default=list)
    missing_fields_json = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    review_reason = Column(Text)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    customer = relationship("Customer", back_populates="research_jobs")
    drafts = relationship(
        "ResearchOutreachDraft",
        back_populates="research_job",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_agent_research_user_status", "user_id", "status", "updated_at"),
        Index("idx_agent_research_customer", "customer_id", "updated_at"),
    )


class ResearchOutreachDraft(Base):
    """Evidence-bound outbound draft; approval never implies delivery."""

    __tablename__ = "research_outreach_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_research_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    channel = Column(String(30), nullable=False)
    language = Column(String(20), nullable=False)
    goal = Column(String(500), nullable=False)
    subject = Column(String(255))
    body = Column(Text, nullable=False)
    personalization_points_json = Column(JSON, nullable=False, default=list)
    evidence_ids_json = Column(JSON, nullable=False, default=list)
    status = Column(String(30), nullable=False, default="draft")
    research_version = Column(Integer, nullable=False)
    resolved_model = Column(String(255))
    resolved_provider = Column(String(100))
    gateway_request_id = Column(String(255))
    usage_json = Column(JSON, nullable=False, default=dict)
    review_reason = Column(Text)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    research_job = relationship("AgentResearchJob", back_populates="drafts")
    deliveries = relationship(
        "AgentOutreachDelivery",
        back_populates="draft",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_research_draft_user_idempotency",
        ),
        Index("idx_research_draft_job_status", "research_job_id", "status"),
    )


class AgentOutreachDelivery(Base):
    """Approval-gated, account-bound delivery snapshot for one research draft."""

    __tablename__ = "agent_outreach_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    draft_id = Column(
        UUID(as_uuid=True),
        ForeignKey("research_outreach_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    channel = Column(String(30), nullable=False)
    provider = Column(String(30), nullable=False)
    account_name = Column(String(100), nullable=False)
    sender = Column(String(255), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255))
    body = Column(Text, nullable=False)
    research_version = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="approval_pending")
    scheduled_at = Column(DateTime, nullable=False)
    outbox_event_id = Column(UUID(as_uuid=True), ForeignKey("outbox_events.id"))
    external_message_id = Column(String(255))
    error_code = Column(String(100))
    review_reason = Column(Text)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    draft = relationship("ResearchOutreachDraft", back_populates="deliveries")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_agent_delivery_user_idempotency",
        ),
        Index("idx_agent_delivery_user_status", "user_id", "status", "updated_at"),
        Index("idx_agent_delivery_account_schedule", "account_id", "scheduled_at"),
    )


class ProspectingJob(Base):
    """Durable, leased orchestration state for a multi-domain search."""

    __tablename__ = "prospecting_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(50), nullable=False, default="hunter")
    status = Column(String(30), nullable=False, default="queued")
    config_json = Column(JSON, nullable=False, default=dict)
    connector_version = Column(Integer, nullable=False)
    page_size = Column(Integer, nullable=False)
    max_pages_per_domain = Column(Integer, nullable=False)
    request_budget = Column(Integer, nullable=False)
    requests_used = Column(Integer, nullable=False, default=0)
    provider_remaining = Column(Float)
    provider_usage_unit = Column(String(30))
    error_code = Column(String(100))
    next_attempt_at = Column(DateTime)
    leased_by = Column(String(100))
    lease_until = Column(DateTime)
    lease_version = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    items = relationship(
        "ProspectingJobItem",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ProspectingJobItem.created_at",
    )

    __table_args__ = (
        Index("idx_prospecting_job_user_created", "user_id", "created_at"),
        Index("idx_prospecting_job_status_due", "status", "next_attempt_at"),
        Index("idx_prospecting_job_lease", "status", "lease_until"),
    )


class ProspectingJobItem(Base):
    """One resumable domain and its committed pagination cursor."""

    __tablename__ = "prospecting_job_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    search_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prospecting_searches.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    domain = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    next_offset = Column(Integer, nullable=False, default=0)
    pages_completed = Column(Integer, nullable=False, default=0)
    requests_used = Column(Integer, nullable=False, default=0)
    contacts_found = Column(Integer, nullable=False, default=0)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    truncated = Column(Boolean, nullable=False, default=False)
    error_code = Column(String(100))
    next_attempt_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    job = relationship("ProspectingJob", back_populates="items")
    search = relationship("ProspectingSearch")

    __table_args__ = (
        UniqueConstraint("job_id", "domain", name="uq_prospecting_job_domain"),
        Index(
            "idx_prospecting_job_item_status_due",
            "job_id",
            "status",
            "next_attempt_at",
        ),
    )


class Conversation(Base):
    """Conversation model"""
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    platform = Column(String(50))  # email, whatsapp, instagram_dm, etc.
    platform_conversation_id = Column(String(255))  # External conversation ID
    status = Column(Enum(ConversationStatus), default=ConversationStatus.ACTIVE)

    # Intent tracking
    intent_level_json = Column(JSON, default={})  # History of intent levels
    current_intent = Column(String(50))  # price_inquiry, collaboration, sample_request, etc.
    intent_confidence = Column(Float, default=0.0)

    # Metadata
    summary = Column(Text)
    tags = Column(JSON, default=[])
    custom_fields = Column(JSON, default={})

    # AI handling
    ai_handled = Column(Boolean, default=False)
    manual_takeover = Column(Boolean, default=False)
    takeover_reason = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime)

    # Relationships
    customer = relationship("Customer", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_conversation_customer_status', 'customer_id', 'status'),
        Index('idx_conversation_platform_id', 'platform', 'platform_conversation_id'),
    )


class Message(Base):
    """Message model"""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    role = Column(String(20))  # user, system, assistant
    content = Column(Text)
    platform_message_id = Column(String(255))

    # AI metadata
    ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Float)
    intent_detected = Column(String(50))
    suggested_actions = Column(JSON, default=[])

    # Status
    sent_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime)
    failed_at = Column(DateTime)
    error_message = Column(Text)

    # Attachments
    attachments = Column(JSON, default=[])

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index('idx_message_conversation_sent', 'conversation_id', 'sent_at'),
    )


class OutreachLog(Base):
    """Outreach log model"""
    __tablename__ = "outreach_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    channel = Column(String(50))  # email, whatsapp
    status = Column(Enum(OutreachStatus), default=OutreachStatus.PENDING)

    # Message info
    message_id = Column(String(255))  # External message ID
    subject = Column(String(255))  # For emails
    content = Column(Text)
    template_id = Column(String(100))

    # Account used
    account_id = Column(Integer)  # Reference to accounts table
    account_type = Column(String(20))  # gmail, outlook, whatsapp_business

    # Scheduling
    scheduled_at = Column(DateTime)
    sent_at = Column(DateTime)

    # Tracking
    delivered_at = Column(DateTime)
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    replied_at = Column(DateTime)
    bounced_at = Column(DateTime)

    # Error handling
    error_msg = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Metrics
    cost = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="outreach_logs")

    __table_args__ = (
        Index('idx_outreach_customer_status', 'customer_id', 'status'),
        Index('idx_outreach_channel_status', 'channel', 'status'),
        Index('idx_outreach_scheduled', 'scheduled_at'),
    )


class Account(Base):
    """Account model for email/WhatsApp credentials"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    account_type = Column(String(20))  # gmail, outlook, whatsapp_business
    name = Column(String(100))
    email = Column(String(255))
    phone_number = Column(String(20))

    # Legacy only. OAuth credentials live in a backend-only 0600 secret file.
    credentials_json = Column(JSON)
    credential_secret_ref = Column(String(1024))
    oauth_subject = Column(String(255))
    oauth_scopes_json = Column(JSON)
    token_expires_at = Column(DateTime)
    connection_status = Column(String(30), nullable=False, default="reconnect_required")
    credential_version = Column(Integer, nullable=False, default=0)
    last_verified_at = Column(DateTime)
    last_error_code = Column(String(100))

    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_used = Column(DateTime)

    # Rate limiting
    daily_limit = Column(Integer, default=100)
    today_sent = Column(Integer, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)

    # Metadata
    labels = Column(JSON, default=[])

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_account_user_type', 'user_id', 'account_type'),
        UniqueConstraint(
            'user_id', 'email', 'account_type', name='uq_account_user_email_type'
        ),
    )


class MailboxOAuthSession(Base):
    """Short-lived, one-time server-side OAuth handshake state."""
    __tablename__ = "mailbox_oauth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String(20), nullable=False)
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    code_verifier_ref = Column(String(1024), nullable=False)
    return_to = Column(String(255), nullable=False, default="/settings")
    status = Column(String(20), nullable=False, default="pending")
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    error_code = Column(String(100))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_mailbox_oauth_user_status", "user_id", "status", "created_at"),
    )


class TaskQueue(Base):
    """Task queue model"""
    __tablename__ = "task_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_type = Column(String(50))  # outreach, check_replies, generate_report, etc.
    payload_json = Column(JSON)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)

    # Priority
    priority = Column(Integer, default=0)  # Higher = more important

    # Scheduling
    scheduled_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Retry handling
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    retry_after = Column(DateTime)

    # Worker info
    worker_id = Column(String(100))
    celery_task_id = Column(String(255), index=True)

    # Error handling
    error_msg = Column(Text)
    error_stack = Column(Text)

    # Dependencies
    depends_on = Column(JSON)  # List of task IDs that must complete first

    # Result
    result_json = Column(JSON)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_task_type_status', 'task_type', 'status'),
        Index('idx_task_scheduled', 'scheduled_at'),
        Index('idx_task_celery_id', 'celery_task_id'),
    )


class Template(Base):
    """Message template model"""
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    template_type = Column(String(20))  # email, whatsapp
    language = Column(String(10), default="en")
    category = Column(String(50))  # introduction, followup, inquiry, etc.

    # Content
    subject_template = Column(String(255))  # For emails
    body_template = Column(Text)
    variables = Column(JSON, default=[])  # List of variable names

    # Usage
    use_count = Column(Integer, default=0)
    success_rate = Column(Float)

    # Status
    is_active = Column(Boolean, default=True)

    # Owner
    user_id = Column(Integer, ForeignKey("users.id"))
    is_default = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Audit log model"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50))  # create, update, delete, execute, pause, resume, takeover
    resource_type = Column(String(50))  # workflow, customer, conversation, etc.
    resource_id = Column(String(255))

    # Details
    details_json = Column(JSON)
    ip_address = Column(String(50))
    user_agent = Column(String(500))

    # Result
    success = Column(Boolean, default=True)
    error_msg = Column(Text)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_created', 'created_at'),
    )


class LLMInvocation(Base):
    """Business invocation without storing raw prompt content."""

    __tablename__ = "llm_invocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    use_case = Column(String(50), nullable=False)
    backend = Column(String(50), nullable=False)
    agent_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id"),
    )
    fencing_token = Column(Integer)
    status = Column(
        Enum(
            LLMInvocationStatus,
            values_callable=lambda values: [value.value for value in values],
            name="llm_invocation_status",
        ),
        nullable=False,
        default=LLMInvocationStatus.PENDING,
    )
    input_hash = Column(String(64), nullable=False)
    output_hash = Column(String(64))
    response_json = Column(JSON)
    workflow_execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id"),
    )
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    error_kind = Column(String(50))
    retryable = Column(Boolean)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    attempts = relationship(
        "LLMAttempt",
        back_populates="invocation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "(agent_run_id IS NULL AND fencing_token IS NULL) OR "
            "(agent_run_id IS NOT NULL AND fencing_token IS NOT NULL)",
            name="ck_llm_invocation_agent_run_fence",
        ),
        Index("idx_llm_invocation_status_created", "status", "created_at"),
        Index("idx_llm_invocation_agent_run", "agent_run_id"),
        Index("idx_llm_invocation_workflow", "workflow_execution_id"),
        Index("idx_llm_invocation_conversation", "conversation_id"),
    )


class LLMAttempt(Base):
    """Provider-level observation associated with an LLM invocation."""

    __tablename__ = "llm_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invocation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("llm_invocations.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number = Column(Integer, nullable=False)
    status = Column(
        Enum(
            LLMAttemptStatus,
            values_callable=lambda values: [value.value for value in values],
            name="llm_attempt_status",
        ),
        nullable=False,
    )
    gateway_request_id = Column(String(255))
    provider = Column(String(100))
    model = Column(String(255))
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost = Column(Float)
    cost_status = Column(String(20), nullable=False, default="unknown")
    cache_hit = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer)
    ttft_ms = Column(Integer)
    e2e_latency_ms = Column(Integer)
    consumer_backpressure_ms = Column(Integer)
    fallback_reason = Column(String(255))
    error_kind = Column(String(50))
    retryable = Column(Boolean)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)

    invocation = relationship("LLMInvocation", back_populates="attempts")

    __table_args__ = (
        UniqueConstraint(
            "invocation_id",
            "attempt_number",
            name="uq_llm_attempt_number",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_llm_attempt_latency_nonnegative",
        ),
        CheckConstraint(
            "ttft_ms IS NULL OR ttft_ms >= 0",
            name="ck_llm_attempt_ttft_nonnegative",
        ),
        CheckConstraint(
            "e2e_latency_ms IS NULL OR e2e_latency_ms >= 0",
            name="ck_llm_attempt_e2e_latency_nonnegative",
        ),
        CheckConstraint(
            "consumer_backpressure_ms IS NULL OR consumer_backpressure_ms >= 0",
            name="ck_llm_attempt_backpressure_nonnegative",
        ),
        Index("idx_llm_attempt_gateway_request", "gateway_request_id"),
        Index("idx_llm_attempt_provider_model", "provider", "model"),
    )


class OutboxEvent(Base):
    """Transactional outbox record for a single external side effect."""

    __tablename__ = "outbox_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type = Column(String(50), nullable=False)
    aggregate_id = Column(String(255), nullable=False)
    event_type = Column(String(50), nullable=False)
    business_key = Column(String(255), nullable=False)
    channel = Column(String(50), nullable=False)
    payload_json = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    status = Column(
        Enum(
            OutboxStatus,
            values_callable=lambda values: [value.value for value in values],
            name="outbox_status",
        ),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    lease_until = Column(DateTime)
    leased_by = Column(String(100))
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    last_error = Column(Text)
    external_message_id = Column(String(255))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    sent_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "channel",
            "business_key",
            "event_type",
            name="uq_outbox_business_action",
        ),
        Index("idx_outbox_dispatch", "status", "available_at"),
        Index("idx_outbox_lease", "status", "lease_until"),
        Index("idx_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )


class OutboxResolutionRequest(Base):
    """One resolution decision scoped to one dead-letter lifecycle."""

    __tablename__ = "outbox_resolution_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outbox_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    dead_letter_version = Column(DateTime, nullable=False)
    action = Column(
        Enum(
            OutboxResolutionAction,
            values_callable=lambda values: [value.value for value in values],
            name="outbox_resolution_action",
        ),
        nullable=False,
    )
    evidence_reference = Column(String(128), nullable=False)
    external_message_id = Column(String(255))
    status = Column(
        Enum(
            OutboxResolutionStatus,
            values_callable=lambda values: [value.value for value in values],
            name="outbox_resolution_status",
        ),
        nullable=False,
        default=OutboxResolutionStatus.PENDING,
    )
    requested_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    executed_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "dead_letter_version",
            name="uq_outbox_resolution_cycle",
        ),
        Index(
            "idx_outbox_resolution_event_status",
            "event_id",
            "status",
        ),
    )


class OutboxResolutionApproval(Base):
    """Approval by one distinct administrator."""

    __tablename__ = "outbox_resolution_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outbox_resolution_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    approved_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "approved_by_user_id",
            name="uq_outbox_resolution_approver",
        ),
        Index("idx_outbox_resolution_approval_request", "request_id"),
    )


class AIRuntimeConfiguration(Base):
    """Versioned, non-secret AI routing configuration applied at request time."""

    __tablename__ = "ai_runtime_configurations"

    id = Column(Integer, primary_key=True, default=1)
    backend = Column(String(20), nullable=False)
    base_url = Column(String(500), nullable=False)
    allowed_providers = Column(JSON, nullable=False, default=list)
    model_aliases = Column(JSON, nullable=False, default=dict)
    timeout_seconds = Column(Float, nullable=False, default=60.0)
    version = Column(Integer, nullable=False, default=1)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class MediaRuntimeRevision(Base):
    """Immutable media-provider configuration captured for reproducible jobs."""

    __tablename__ = "media_runtime_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    revision = Column(Integer, nullable=False)
    provider = Column(String(30), nullable=False)
    enabled_modes = Column(JSON, nullable=False, default=list)
    model_aliases = Column(JSON, nullable=False, default=dict)
    capability_snapshot = Column(JSON, nullable=False, default=dict)
    capability_snapshot_hash = Column(String(64), nullable=False)
    pricing_snapshot = Column(JSON, nullable=False, default=dict)
    pricing_snapshot_hash = Column(
        String(64),
        nullable=False,
        default="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "revision > 0",
            name="ck_media_runtime_revision_positive",
        ),
        CheckConstraint(
            "provider = 'fal'",
            name="ck_media_runtime_provider_supported",
        ),
        UniqueConstraint(
            "org_id",
            "revision",
            name="uq_media_runtime_org_revision",
        ),
        Index("idx_media_runtime_revision_org_created", "org_id", "created_at"),
    )


class MediaRuntimeProbeRecord(Base):
    """Append-only, secret-free health evidence for one runtime revision."""

    __tablename__ = "media_runtime_probe_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_runtime_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    ready = Column(Boolean, nullable=False)
    reachable = Column(Boolean, nullable=False)
    issues = Column(JSON, nullable=False, default=list)
    capability_snapshot_hash = Column(String(64), nullable=False)
    probed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index(
            "idx_media_runtime_probe_revision_created",
            "revision_id",
            "created_at",
        ),
    )


class MediaRuntimeActivation(Base):
    """Mutable pointer; referenced revisions and their job contracts stay immutable."""

    __tablename__ = "media_runtime_activations"

    org_id = Column(UUID(as_uuid=True), primary_key=True)
    active_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_runtime_revisions.id"),
        nullable=False,
    )
    activated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    activated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MediaBudgetAccount(Base):
    """Locked monthly balance used to reserve expensive media work atomically."""

    __tablename__ = "media_budget_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    period_start = Column(Date, nullable=False)
    limit_microusd = Column(BigInteger, nullable=False)
    reserved_microusd = Column(BigInteger, nullable=False, default=0)
    spent_microusd = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            "limit_microusd >= 0 AND reserved_microusd >= 0 "
            "AND spent_microusd >= 0",
            name="ck_media_budget_nonnegative",
        ),
        UniqueConstraint(
            "org_id",
            "period_start",
            name="uq_media_budget_org_period",
        ),
    )


class MediaGenerationJob(Base):
    """Durable, fenced generation intent with no raw prompt or provider secret."""

    __tablename__ = "media_generation_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    storyboard_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_storyboard_versions.id"),
        nullable=False,
    )
    shot_id = Column(UUID(as_uuid=True), nullable=False)
    runtime_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_runtime_revisions.id"),
        nullable=False,
    )
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    intent_hash = Column(String(64), nullable=False)
    payload_ref = Column(String(1000), nullable=False)
    mode = Column(String(40), nullable=False)
    provider = Column(String(30), nullable=False)
    model_id = Column(String(255), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    effect_state = Column(String(20), nullable=False, default="none")
    fencing_token = Column(Integer, nullable=False, default=0)
    leased_by = Column(String(100))
    lease_until = Column(DateTime)
    heartbeat_at = Column(DateTime)
    event_sequence = Column(Integer, nullable=False, default=0)
    reserved_cost_microusd = Column(BigInteger, nullable=False)
    estimate_hash = Column(String(64), nullable=False)
    budget_period_start = Column(Date, nullable=False)
    actual_cost_microusd = Column(BigInteger)
    budget_finalized_at = Column(DateTime)
    provider_request_id = Column(String(255))
    provider_state = Column(String(30))
    reconcile_count = Column(Integer, nullable=False, default=0)
    next_reconcile_at = Column(DateTime)
    last_reconciled_at = Column(DateTime)
    reconciliation_fencing_token = Column(Integer, nullable=False, default=0)
    reconciliation_leased_by = Column(String(100))
    reconciliation_lease_until = Column(DateTime)
    result_ref = Column(String(1000))
    error_code = Column(String(100))
    deadline_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    attempts = relationship(
        "MediaGenerationAttempt",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="MediaGenerationAttempt.attempt_number",
    )
    events = relationship(
        "MediaGenerationEvent",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="MediaGenerationEvent.sequence",
    )

    __table_args__ = (
        CheckConstraint(
            "reserved_cost_microusd >= 0",
            name="ck_media_job_reserved_cost_nonnegative",
        ),
        UniqueConstraint(
            "org_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_media_job_scope_idempotency",
        ),
        Index("idx_media_job_dispatch", "status", "created_at"),
        Index(
            "idx_media_job_reconciliation",
            "status",
            "next_reconcile_at",
        ),
        Index("idx_media_job_org_created", "org_id", "created_at"),
    )


class MediaGenerationAttempt(Base):
    """One external submission effect; request IDs are globally deduplicated."""

    __tablename__ = "media_generation_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number = Column(Integer, nullable=False)
    fencing_token = Column(Integer, nullable=False)
    provider = Column(String(30), nullable=False)
    model_id = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False)
    effect_state = Column(String(20), nullable=False)
    provider_request_id = Column(String(255))
    error_code = Column(String(100))
    started_at = Column(DateTime, nullable=False)
    submitted_at = Column(DateTime)
    completed_at = Column(DateTime)

    job = relationship("MediaGenerationJob", back_populates="attempts")

    __table_args__ = (
        CheckConstraint(
            "attempt_number > 0",
            name="ck_media_attempt_number_positive",
        ),
        UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_media_attempt_job_number",
        ),
        UniqueConstraint(
            "provider",
            "provider_request_id",
            name="uq_media_attempt_provider_request",
        ),
    )


class MediaGenerationEvent(Base):
    """Append-only, ordered and secret-free job audit event."""

    __tablename__ = "media_generation_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    data_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    job = relationship("MediaGenerationJob", back_populates="events")

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "sequence",
            name="uq_media_event_job_sequence",
        ),
        Index("idx_media_event_job_created", "job_id", "created_at"),
    )


class MediaCallbackInbox(Base):
    """Deduplicated, secret-free proof that a provider callback was verified."""

    __tablename__ = "media_callback_inbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(30), nullable=False)
    provider_account_ref_hash = Column(String(64), nullable=False)
    provider_request_id = Column(String(255), nullable=False)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="SET NULL"),
    )
    body_sha256 = Column(String(64), nullable=False)
    delivery_hint = Column(String(20), nullable=False)
    signature_timestamp = Column(DateTime, nullable=False)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_account_ref_hash",
            "provider_request_id",
            name="uq_media_callback_provider_account_request",
        ),
        Index("idx_media_callback_job_received", "job_id", "received_at"),
    )


class MediaProviderUsageReceipt(Base):
    """Provider-bound usage units awaiting an immutable pricing snapshot."""

    __tablename__ = "media_provider_usage_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    runtime_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_runtime_revisions.id"),
        nullable=False,
    )
    provider = Column(String(30), nullable=False)
    provider_request_id = Column(String(255), nullable=False)
    model_id = Column(String(255), nullable=False)
    billable_units = Column(Numeric(21, 9), nullable=False)
    pricing_status = Column(String(20), nullable=False, default="unpriced")
    unit_price_microusd = Column(BigInteger)
    cost_microusd = Column(BigInteger)
    receipt_hash = Column(String(64), nullable=False)
    pricing_snapshot_hash = Column(String(64))
    observed_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "billable_units >= 0",
            name="ck_media_usage_billable_units_nonnegative",
        ),
        UniqueConstraint(
            "provider",
            "provider_request_id",
            name="uq_media_usage_provider_request",
        ),
        UniqueConstraint("job_id", name="uq_media_usage_job"),
        Index("idx_media_usage_runtime_model", "runtime_revision_id", "model_id"),
    )


class MediaSubmissionResolutionRequest(Base):
    """One immutable conclusion for one submission-unknown lifecycle."""

    __tablename__ = "media_submission_resolution_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_unknown_version = Column(DateTime, nullable=False)
    action = Column(
        Enum(
            MediaSubmissionResolutionAction,
            values_callable=lambda values: [value.value for value in values],
            name="media_submission_resolution_action",
        ),
        nullable=False,
    )
    evidence_reference = Column(String(128), nullable=False)
    provider_request_id = Column(String(128))
    status = Column(
        Enum(
            MediaSubmissionResolutionStatus,
            values_callable=lambda values: [value.value for value in values],
            name="media_submission_resolution_status",
        ),
        nullable=False,
        default=MediaSubmissionResolutionStatus.PENDING,
    )
    requested_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    executed_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "submission_unknown_version",
            name="uq_media_submission_resolution_cycle",
        ),
        Index(
            "idx_media_submission_resolution_job_status",
            "job_id",
            "status",
        ),
    )


class MediaSubmissionResolutionApproval(Base):
    """Approval by one distinct administrator."""

    __tablename__ = "media_submission_resolution_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "media_submission_resolution_requests.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    approved_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "approved_by_user_id",
            name="uq_media_submission_resolution_approver",
        ),
        Index(
            "idx_media_submission_resolution_approval_request",
            "request_id",
        ),
    )


class MediaBudgetLedgerEntry(Base):
    """Append-only budget evidence; integer micro-USD avoids float drift."""

    __tablename__ = "media_budget_ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start = Column(Date, nullable=False)
    entry_type = Column(String(30), nullable=False)
    amount_microusd = Column(BigInteger, nullable=False)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    estimate_hash = Column(String(64))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "amount_microusd >= 0",
            name="ck_media_ledger_amount_nonnegative",
        ),
        Index("idx_media_ledger_org_period", "org_id", "period_start"),
    )


class AIChatSession(Base):
    """Private workspace chat owned by one authenticated user."""

    __tablename__ = "ai_chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(160), nullable=False, default="New conversation")
    use_case = Column(String(50), nullable=False, default="live_reply")
    generation_epoch = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    messages = relationship(
        "AIChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AIChatMessage.created_at",
    )
    turns = relationship(
        "AgentTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentTurn.sequence",
    )

    __table_args__ = (
        Index("idx_ai_chat_session_user_updated", "user_id", "updated_at"),
    )


class AgentTurn(Base):
    """Durable, fenced generation within an operator chat session."""

    __tablename__ = "agent_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    generation_epoch = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    status = Column(String(30), nullable=False, default="running")
    user_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_messages.id"),
    )
    assistant_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_messages.id"),
    )
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)

    session = relationship("AIChatSession", back_populates="turns")

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_agent_turn_session_sequence",
        ),
        UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_agent_turn_session_idempotency",
        ),
        Index(
            "uq_agent_turn_active_session",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index("idx_agent_turn_session_status", "session_id", "status"),
    )


class AIChatMessage(Base):
    """One persisted user or assistant turn in the operator chat."""

    __tablename__ = "ai_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    resolved_model = Column(String(255))
    resolved_provider = Column(String(100))
    gateway_request_id = Column(String(255))
    usage_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("AIChatSession", back_populates="messages")

    __table_args__ = (
        Index("idx_ai_chat_message_session_created", "session_id", "created_at"),
    )


class AgentMemoryEpoch(Base):
    """Monotonic invalidation fence for one fully-qualified memory scope."""

    __tablename__ = "agent_memory_epochs"

    scope_key = Column(String(64), primary_key=True)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(Integer)
    session_id = Column(UUID(as_uuid=True))
    epoch = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_agent_memory_epoch_org", "org_id"),
    )


class AgentMemory(Base):
    """Durable source record for working, session, and long-term memory."""

    __tablename__ = "agent_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_key = Column(String(64), nullable=False)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(Integer)
    session_id = Column(UUID(as_uuid=True))
    tier = Column(String(20), nullable=False)
    kind = Column(String(100), nullable=False)
    content = Column(JSON, nullable=False)
    source_type = Column(String(60), nullable=False)
    source_ref = Column(String(500), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="active")
    correction_of = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_memories.id"),
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index(
            "idx_agent_memory_scope_status_tier",
            "scope_key",
            "status",
            "tier",
        ),
        Index("idx_agent_memory_org_created", "org_id", "created_at"),
    )


class AgentMemoryPurgeJob(Base):
    """Durable cleanup work for indexes and caches derived from memory."""

    __tablename__ = "agent_memory_purge_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_memories.id"),
        nullable=False,
    )
    tombstone_epoch = Column(Integer, nullable=False)
    targets = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("idx_agent_memory_purge_status_created", "status", "created_at"),
    )


class KnowledgeDocument(Base):
    """Immutable version of one tenant-owned knowledge document."""

    __tablename__ = "knowledge_documents"

    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    source_ref = Column(String(500), nullable=False)
    title = Column(String(300), nullable=False)
    authority = Column(String(60), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    acl_policy_version = Column(String(64), nullable=False)
    index_version = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version",
            name="uq_knowledge_document_version",
        ),
        Index(
            "idx_knowledge_document_org_status_source",
            "org_id",
            "status",
            "source_ref",
        ),
    )


class KnowledgeChunk(Base):
    """Searchable text unit belonging to an immutable document version."""

    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.record_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    source_ref = Column(String(600), nullable=False)
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "document_record_id",
            "chunk_id",
            name="uq_knowledge_chunk_document_chunk",
        ),
        Index("idx_knowledge_chunk_document", "document_record_id"),
    )


class KnowledgeDocumentGrant(Base):
    """Version-bound role or user grant used by authoritative ACL checks."""

    __tablename__ = "knowledge_document_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.record_id", ondelete="CASCADE"),
        nullable=False,
    )
    principal_type = Column(String(20), nullable=False)
    principal_value = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "document_record_id",
            "principal_type",
            "principal_value",
            name="uq_knowledge_document_grant",
        ),
        Index(
            "idx_knowledge_grant_document_principal",
            "document_record_id",
            "principal_type",
            "principal_value",
        ),
    )


class AgentToolExecution(Base):
    """Durable, fenced lifecycle for one server-authorized tool call."""

    __tablename__ = "agent_tool_executions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    idempotency_key = Column(String(69), nullable=False, unique=True)
    input_hash = Column(String(64), nullable=False)
    run_id = Column(UUID(as_uuid=True), nullable=False)
    turn_id = Column(UUID(as_uuid=True), nullable=False)
    generation_epoch = Column(Integer, nullable=False)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    actor_user_id = Column(Integer, nullable=False)
    tool_name = Column(String(128), nullable=False)
    tool_version = Column(String(30), nullable=False)
    risk = Column(String(20), nullable=False)
    arguments = Column(JSON, nullable=False)
    provenance = Column(JSON, nullable=False)
    purpose = Column(String(255), nullable=False)
    approval_required = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False)
    approved_by_user_id = Column(Integer)
    approval_entitlements_hash = Column(String(64))
    approved_at = Column(DateTime)
    result_json = Column(JSON)
    result_hash = Column(String(64))
    error_code = Column(String(100))
    outbox_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outbox_events.id"),
        unique=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("idx_agent_tool_run_status", "run_id", "status"),
        Index("idx_agent_tool_turn_status", "turn_id", "status"),
        Index("idx_agent_tool_org_created", "org_id", "created_at"),
    )


class AgentRun(Base):
    """Durable lease and recovery state for one agent execution."""

    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    input_hash = Column(String(64), nullable=False)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(Integer, nullable=False)
    session_id = Column(UUID(as_uuid=True))
    turn_id = Column(UUID(as_uuid=True))
    use_case = Column(String(50), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    generation_epoch = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    fencing_token = Column(Integer, nullable=False, default=0)
    leased_by = Column(String(100))
    lease_until = Column(DateTime)
    heartbeat_at = Column(DateTime)
    effect_state = Column(String(20), nullable=False, default="none")
    state_json = Column(JSON, nullable=False, default=dict)
    event_sequence = Column(Integer, nullable=False, default=0)
    event_bytes = Column(Integer, nullable=False, default=0)
    deadline_at = Column(DateTime, nullable=False)
    error_code = Column(String(100))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("idx_agent_run_status_deadline", "status", "deadline_at"),
        Index("idx_agent_run_status_lease", "status", "lease_until"),
        Index("idx_agent_run_org_created", "org_id", "created_at"),
    )


class AgentRunEvent(Base):
    """Durable, ordered user-visible event emitted by an agent run."""

    __tablename__ = "agent_run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    data_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_run_event_sequence",
        ),
        Index("idx_agent_run_event_replay", "run_id", "sequence"),
        Index("idx_agent_run_event_expiry", "expires_at"),
    )


class VideoPersona(Base):
    """Tenant-owned logical persona whose revisions are immutable records."""

    __tablename__ = "video_personas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    retired_at = Column(DateTime)

    __table_args__ = (
        Index("idx_video_persona_org_created", "org_id", "created_at"),
    )


class VideoPersonaVersion(Base):
    """Immutable persona payload plus independent approval evidence."""

    __tablename__ = "video_persona_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_personas.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id = Column(UUID(as_uuid=True), nullable=False)
    revision = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    spec_json = Column(JSON, nullable=False)
    spec_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_by_user_id = Column(Integer, nullable=False)
    approved_by_user_id = Column(Integer)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            "revision",
            name="uq_video_persona_revision",
        ),
        UniqueConstraint(
            "org_id",
            "created_by_user_id",
            "idempotency_key",
            name="uq_video_persona_scope_idempotency",
        ),
        CheckConstraint("revision > 0", name="ck_video_persona_revision_positive"),
        Index(
            "idx_video_persona_version_persona_status",
            "persona_id",
            "status",
            "revision",
        ),
        Index("idx_video_persona_version_org_created", "org_id", "created_at"),
    )


class VideoProject(Base):
    """Project pinned to one approved persona snapshot."""

    __tablename__ = "video_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    brief_json = Column(JSON, nullable=False)
    brief_hash = Column(String(64), nullable=False)
    persona_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_persona_versions.id"),
        nullable=False,
    )
    persona_snapshot_json = Column(JSON, nullable=False)
    persona_spec_hash = Column(String(64), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_video_project_scope_idempotency",
        ),
        Index("idx_video_project_org_created", "org_id", "created_at"),
        Index("idx_video_project_persona", "persona_version_id"),
    )


class VideoProjectEvidence(Base):
    """Immutable, ACL-authorized knowledge snapshot allowed for one project."""

    __tablename__ = "video_project_evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id = Column(UUID(as_uuid=True), nullable=False)
    knowledge_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.record_id"),
        nullable=False,
    )
    document_id = Column(UUID(as_uuid=True), nullable=False)
    document_version = Column(Integer, nullable=False)
    source_ref = Column(String(500), nullable=False)
    title = Column(String(300), nullable=False)
    authority = Column(String(60), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    acl_policy_version = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    added_by_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "knowledge_record_id",
            name="uq_video_project_evidence_record",
        ),
        Index("idx_video_project_evidence_project", "project_id"),
    )


class VideoStoryboardVersion(Base):
    """Immutable storyboard revision with independent approval."""

    __tablename__ = "video_storyboard_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("video_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id = Column(UUID(as_uuid=True), nullable=False)
    revision = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    storyboard_json = Column(JSON, nullable=False)
    storyboard_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_by_user_id = Column(Integer, nullable=False)
    approved_by_user_id = Column(Integer)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "revision",
            name="uq_video_storyboard_revision",
        ),
        UniqueConstraint(
            "org_id",
            "created_by_user_id",
            "idempotency_key",
            name="uq_video_storyboard_scope_idempotency",
        ),
        CheckConstraint(
            "revision > 0",
            name="ck_video_storyboard_revision_positive",
        ),
        Index(
            "idx_video_storyboard_project_status",
            "project_id",
            "status",
            "revision",
        ),
    )


class MediaUploadIntent(Base):
    """Server-keyed, one-use upload intent for a quarantined object."""

    __tablename__ = "media_upload_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    actor_user_id = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    input_hash = Column(String(64), nullable=False)
    storage_key = Column(String(1000), nullable=False, unique=True)
    kind = Column(String(30), nullable=False)
    expected_mime_type = Column(String(255), nullable=False)
    expected_size_bytes = Column(BigInteger, nullable=False)
    expected_sha256 = Column(String(64), nullable=False)
    sensitivity = Column(String(20), nullable=False)
    consent_required = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="pending")
    asset_id = Column(UUID(as_uuid=True), ForeignKey("media_assets.id"))
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_media_upload_scope_idempotency",
        ),
        Index("idx_media_upload_status_expiry", "status", "expires_at"),
        Index("idx_media_upload_org_created", "org_id", "created_at"),
    )


class MediaAsset(Base):
    """Immutable media object metadata and its quarantine state."""

    __tablename__ = "media_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    kind = Column(String(30), nullable=False)
    source = Column(String(30), nullable=False)
    storage_backend = Column(String(50), nullable=False)
    storage_key = Column(String(1000), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    mime_type = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sensitivity = Column(String(20), nullable=False)
    quarantined = Column(Boolean, nullable=False, default=True)
    scan_status = Column(String(30), nullable=False, default="pending")
    rights_status = Column(String(30), nullable=False, default="unknown")
    consent_required = Column(Boolean, nullable=False, default=False)
    consent_status = Column(String(30), nullable=False, default="unknown")
    scan_report_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "media_scan_reports.id",
            name="fk_media_asset_scan_report",
            use_alter=True,
        ),
    )
    rights_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "media_rights_records.id",
            name="fk_media_asset_rights_record",
            use_alter=True,
        ),
    )
    consent_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "media_consent_records.id",
            name="fk_media_asset_consent_record",
            use_alter=True,
        ),
    )
    metadata_json = Column(JSON, nullable=False, default=dict)
    reviewed_by_user_id = Column(Integer)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = Column(DateTime)

    __table_args__ = (
        Index("idx_media_asset_org_created", "org_id", "created_at"),
        Index("idx_media_asset_org_hash", "org_id", "sha256"),
        Index("idx_media_asset_quarantine", "quarantined", "scan_status"),
        CheckConstraint("size_bytes > 0", name="ck_media_asset_size_positive"),
    )


class MediaScanReport(Base):
    """Immutable malware/content scan evidence bound to an asset checksum."""

    __tablename__ = "media_scan_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    scanner = Column(String(100), nullable=False)
    scanner_version = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)
    asset_sha256 = Column(String(64), nullable=False)
    findings_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_media_scan_asset_created", "asset_id", "created_at"),
        Index("idx_media_scan_org_status", "org_id", "status"),
    )


class MediaRightsRecord(Base):
    """Auditable usage-rights decision with scope and validity window."""

    __tablename__ = "media_rights_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(30), nullable=False)
    basis = Column(String(100), nullable=False)
    territories = Column(JSON, nullable=False, default=list)
    channels = Column(JSON, nullable=False, default=list)
    source_ref = Column(String(500), nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime)
    reviewed_by_user_id = Column(Integer, nullable=False)
    revoked_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_media_rights_asset_created", "asset_id", "created_at"),
        Index("idx_media_rights_org_status", "org_id", "status"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_media_rights_valid_range",
        ),
    )


class MediaAssetRelation(Base):
    """Generation and derivation lineage between immutable media assets."""

    __tablename__ = "media_asset_relations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    parent_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "parent_asset_id",
            "child_asset_id",
            "relation_type",
            name="uq_media_asset_relation",
        ),
        CheckConstraint(
            "parent_asset_id <> child_asset_id",
            name="ck_media_asset_relation_not_self",
        ),
        Index("idx_media_asset_relation_child", "child_asset_id"),
    )


class MediaConsentRecord(Base):
    """Evidence-backed consent scope; never represented as a boolean alone."""

    __tablename__ = "media_consent_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_ref = Column(String(255), nullable=False)
    purpose = Column(String(500), nullable=False)
    regions = Column(JSON, nullable=False, default=list)
    media_types = Column(JSON, nullable=False, default=list)
    status = Column(String(30), nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime)
    evidence_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_assets.id"),
        nullable=False,
    )
    created_by_user_id = Column(Integer, nullable=False)
    revoked_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_media_consent_org_status", "org_id", "status"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_media_consent_valid_range",
        ),
    )


class StatsDaily(Base):
    """Daily statistics model"""
    __tablename__ = "stats_daily"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, index=True)  # Only date part matters

    # Customer stats
    new_customers = Column(Integer, default=0)
    active_customers = Column(Integer, default=0)
    converted_customers = Column(Integer, default=0)

    # Outreach stats
    emails_sent = Column(Integer, default=0)
    whatsapp_sent = Column(Integer, default=0)
    emails_opened = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)

    # Conversation stats
    new_conversations = Column(Integer, default=0)
    active_conversations = Column(Integer, default=0)
    ai_handled = Column(Integer, default=0)
    manual_takeovers = Column(Integer, default=0)

    # Workflow stats
    workflows_executed = Column(Integer, default=0)
    workflows_completed = Column(Integer, default=0)
    workflows_failed = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_stats_user_date'),
    )


class SalesOpportunity(Base):
    """Qualified inquiry that carries a lead from conversation to a won order."""

    __tablename__ = "sales_opportunities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
    )
    title = Column(String(255), nullable=False)
    source = Column(String(30), nullable=False, default="manual")
    stage = Column(String(30), nullable=False, default="inquiry")
    inquiry_summary = Column(Text)
    requirements_json = Column(JSON, nullable=False, default=dict)
    estimated_value = Column(Numeric(14, 2))
    currency = Column(String(3), nullable=False, default="USD")
    expected_close_date = Column(Date)
    lost_reason = Column(Text)
    won_at = Column(DateTime)
    closed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    customer = relationship("Customer")
    quotations = relationship(
        "SalesQuotation",
        back_populates="opportunity",
        cascade="all, delete-orphan",
        order_by="SalesQuotation.revision",
    )

    __table_args__ = (
        Index("idx_sales_opportunity_user_stage", "user_id", "stage", "updated_at"),
        Index("idx_sales_opportunity_customer", "customer_id"),
    )


class SalesQuotation(Base):
    """Immutable-once-submitted quotation revision; acceptance creates the order."""

    __tablename__ = "sales_quotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quote_number = Column(String(40), nullable=False, unique=True)
    revision = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False, default="draft")
    currency = Column(String(3), nullable=False)
    incoterm = Column(String(10), nullable=False)
    payment_terms = Column(String(255), nullable=False)
    deposit_percent = Column(Integer, nullable=False, default=30)
    lead_time_days = Column(Integer, nullable=False)
    valid_until = Column(Date, nullable=False)
    line_items_json = Column(JSON, nullable=False, default=list)
    subtotal = Column(Numeric(14, 2), nullable=False)
    freight_amount = Column(Numeric(14, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total = Column(Numeric(14, 2), nullable=False)
    total_cost = Column(Numeric(14, 2))
    margin_percent = Column(Numeric(7, 2))
    notes = Column(Text)
    review_reason = Column(Text)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    sent_at = Column(DateTime)
    sent_channel = Column(String(30))
    accepted_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    opportunity = relationship("SalesOpportunity", back_populates="quotations")

    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "revision",
            name="uq_sales_quotation_revision",
        ),
        Index("idx_sales_quotation_status", "status", "valid_until"),
        CheckConstraint(
            "deposit_percent >= 0 AND deposit_percent <= 100",
            name="ck_sales_quotation_deposit_percent",
        ),
    )


class SalesOrder(Base):
    """Confirmed order snapshot frozen from one accepted quotation."""

    __tablename__ = "sales_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    opportunity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_opportunities.id"),
        nullable=False,
    )
    quotation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_quotations.id"),
        nullable=False,
        unique=True,
    )
    order_number = Column(String(40), nullable=False, unique=True)
    customer_po_number = Column(String(100))
    status = Column(String(30), nullable=False, default="awaiting_deposit")
    fulfillment_mode = Column(String(20), nullable=False, default="in_house")
    currency = Column(String(3), nullable=False)
    incoterm = Column(String(10), nullable=False)
    payment_terms = Column(String(255), nullable=False)
    line_items_json = Column(JSON, nullable=False, default=list)
    total = Column(Numeric(14, 2), nullable=False)
    deposit_required = Column(Numeric(14, 2), nullable=False)
    balance_before_shipment = Column(Boolean, nullable=False, default=True)
    required_ship_date = Column(Date)
    shipping_address = Column(Text)
    cancel_reason = Column(Text)
    production_started_at = Column(DateTime)
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    customer = relationship("Customer")
    production_tasks = relationship(
        "ProductionTask",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ProductionTask.created_at",
    )
    inspections = relationship(
        "QualityInspection",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="QualityInspection.created_at",
    )
    shipments = relationship(
        "OrderShipment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderShipment.created_at",
    )
    payments = relationship(
        "OrderPayment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderPayment.received_at",
    )

    __table_args__ = (
        Index("idx_sales_order_user_status", "user_id", "status", "updated_at"),
        Index("idx_sales_order_ship_date", "status", "required_ship_date"),
    )


class ProductionTask(Base):
    """In-house work order or outsourced supplier purchase order for an order."""

    __tablename__ = "production_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(20), nullable=False)
    reference_number = Column(String(40), nullable=False, unique=True)
    description = Column(String(500), nullable=False)
    supplier_name = Column(String(255))
    production_line = Column(String(100))
    quantity = Column(Numeric(14, 3), nullable=False)
    unit = Column(String(20), nullable=False, default="pcs")
    status = Column(String(30), nullable=False, default="planned")
    progress_percent = Column(Integer, nullable=False, default=0)
    planned_start = Column(Date)
    planned_finish = Column(Date)
    actual_start = Column(DateTime)
    actual_finish = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    order = relationship("SalesOrder", back_populates="production_tasks")

    __table_args__ = (
        Index("idx_production_task_order_status", "order_id", "status"),
        Index("idx_production_task_finish", "status", "planned_finish"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_production_task_progress",
        ),
    )


class QualityInspection(Base):
    """Recorded QC result; a passed final inspection gates shipment."""

    __tablename__ = "quality_inspections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    production_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("production_tasks.id", ondelete="SET NULL"),
    )
    stage = Column(String(30), nullable=False)
    result = Column(String(20), nullable=False)
    inspector = Column(String(255), nullable=False)
    sample_size = Column(Integer)
    defects_json = Column(JSON, nullable=False, default=list)
    report_url = Column(String(1000))
    notes = Column(Text)
    inspected_at = Column(DateTime, nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    order = relationship("SalesOrder", back_populates="inspections")

    __table_args__ = (
        Index("idx_quality_inspection_order", "order_id", "stage", "inspected_at"),
    )


class OrderShipment(Base):
    """Shipment booking and carrier tracking for an order."""

    __tablename__ = "order_shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    shipment_number = Column(String(40), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="booked")
    transport_mode = Column(String(20), nullable=False)
    carrier = Column(String(255), nullable=False)
    tracking_number = Column(String(255))
    bill_of_lading = Column(String(255))
    container_number = Column(String(100))
    port_of_loading = Column(String(255))
    port_of_discharge = Column(String(255))
    etd = Column(Date)
    eta = Column(Date)
    departed_at = Column(DateTime)
    delivered_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    order = relationship("SalesOrder", back_populates="shipments")

    __table_args__ = (
        Index("idx_order_shipment_order_status", "order_id", "status"),
    )


class OrderPayment(Base):
    """Received customer payment; payments gate production and shipment."""

    __tablename__ = "order_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    kind = Column(String(20), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    method = Column(String(30), nullable=False)
    reference = Column(String(255))
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    order = relationship("SalesOrder", back_populates="payments")

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "idempotency_key",
            name="uq_order_payment_idempotency",
        ),
        CheckConstraint("amount > 0", name="ck_order_payment_amount_positive"),
    )


class FulfillmentEvent(Base):
    """Append-only lead-to-delivery timeline across opportunities and orders."""

    __tablename__ = "fulfillment_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
    )
    actor_user_id = Column(Integer, ForeignKey("users.id"))
    event_type = Column(String(60), nullable=False)
    from_status = Column(String(30))
    to_status = Column(String(30))
    payload_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_fulfillment_event_opportunity", "opportunity_id", "created_at"),
        Index("idx_fulfillment_event_order", "order_id", "created_at"),
    )


class CatalogProduct(Base):
    """Sellable catalog record: a plain product, an option family, or one of its variants."""

    __tablename__ = "catalog_products"

    id = Column(String(80), primary_key=True)
    parent_id = Column(
        String(80),
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
    )
    title = Column(String(255), nullable=False)
    brand = Column(String(100))
    category = Column(String(100), index=True)
    status = Column(String(20), nullable=False, default="active")
    short_description = Column(String(500))
    long_description = Column(Text)
    attributes_json = Column(JSON, nullable=False, default=dict)
    specs_json = Column(JSON, nullable=False, default=dict)
    options_json = Column(JSON, nullable=False, default=dict)
    option_values_json = Column(JSON, nullable=False, default=dict)
    labels_json = Column(JSON, nullable=False, default=list)
    price = Column(Numeric(14, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    unit_cost = Column(Numeric(14, 4))
    min_price = Column(Numeric(14, 4))
    moq = Column(Integer, nullable=False, default=1)
    lead_time_days = Column(Integer)
    stock = Column(Integer, nullable=False, default=0)
    reorder_point = Column(Integer, nullable=False, default=0)
    sales_last_30d = Column(Integer, nullable=False, default=0)
    image_url = Column(String(1000))
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    variants = relationship(
        "CatalogProduct",
        cascade="all, delete-orphan",
        order_by="CatalogProduct.id",
        back_populates="parent",
    )
    parent = relationship("CatalogProduct", remote_side=[id], back_populates="variants")

    __table_args__ = (
        Index("idx_catalog_product_parent", "parent_id"),
        Index("idx_catalog_product_status_category", "status", "category"),
        CheckConstraint("price >= 0", name="ck_catalog_product_price"),
        CheckConstraint("moq >= 1", name="ck_catalog_product_moq"),
    )


class TradeTerm(Base):
    """One versioned trade-terms passage; only the version in force at the clock is quoted."""

    __tablename__ = "trade_terms"

    id = Column(String(80), primary_key=True)
    source_id = Column(String(80), nullable=False)
    version = Column(String(20), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(50))
    content = Column(Text, nullable=False)
    effective_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_id", "version", name="uq_trade_term_source_version"),
        Index("idx_trade_term_source", "source_id", "effective_at"),
    )


class MarketingCampaign(Base):
    """Outbound marketing campaign the operations assistant reports on and drafts."""

    __tablename__ = "marketing_campaigns"

    id = Column(String(40), primary_key=True)
    name = Column(String(80), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    objective = Column(String(200))
    channel = Column(String(50))
    audience = Column(String(300))
    copy_text = Column(String(600))
    budget = Column(Numeric(14, 2), nullable=False, default=0)
    spend = Column(Numeric(14, 2))
    revenue = Column(Numeric(14, 2))
    currency = Column(String(3), nullable=False, default="USD")
    starts = Column(Date)
    ends = Column(Date)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class CatalogPromotion(Base):
    """Approved price promotion over catalog listings."""

    __tablename__ = "catalog_promotions"

    id = Column(String(40), primary_key=True)
    name = Column(String(80), nullable=False)
    listing_ids_json = Column(JSON, nullable=False, default=list)
    discount_pct = Column(Numeric(6, 2), nullable=False)
    starts = Column(Date, nullable=False)
    ends = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="scheduled")
    change_id = Column(String(40))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CommerceSession(Base):
    """One assistant conversation: provenance state, transcript and pending app events."""

    __tablename__ = "commerce_sessions"

    id = Column(String(64), primary_key=True)
    role = Column(String(20), nullable=False)
    subject_id = Column(String(80), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))
    invite_id = Column(UUID(as_uuid=True), ForeignKey("buyer_portal_invites.id", ondelete="CASCADE"))
    state_json = Column(JSON, nullable=False, default=dict)
    pending_app_events_json = Column(JSON, nullable=False, default=list)
    messages_json = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_commerce_session_subject", "role", "subject_id", "updated_at"),
    )


class CommerceCartLine(Base):
    """A buyer's RFQ basket line, kept per customer across sessions."""

    __tablename__ = "commerce_cart_lines"

    id = Column(Integer, primary_key=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        String(80),
        ForeignKey("catalog_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("customer_id", "product_id", name="uq_commerce_cart_line"),
        CheckConstraint("quantity >= 1", name="ck_commerce_cart_quantity"),
    )


class CommerceStagedChange(Base):
    """Durable ledger of operations-assistant changes awaiting operator approval."""

    __tablename__ = "commerce_staged_changes"

    id = Column(String(40), primary_key=True)
    kind = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False)
    document_json = Column(JSON, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_commerce_staged_change_status", "status", "created_at"),
    )


class CommerceMemoryFact(Base):
    """One remembered buyer or operator fact, validated by the commerce write filter."""

    __tablename__ = "commerce_memory_facts"

    id = Column(Integer, primary_key=True)
    subject_id = Column(String(80), nullable=False)
    key = Column(String(64), nullable=False)
    value = Column(String(200), nullable=False)
    category = Column(String(20), nullable=False)
    source_session_id = Column(String(80))
    updated_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("subject_id", "key", name="uq_commerce_memory_subject_key"),
    )


class CommerceMemoryPurge(Base):
    """How many times a memory subject was purged; extraction discards stale batches."""

    __tablename__ = "commerce_memory_purges"

    subject_id = Column(String(80), primary_key=True)
    generation = Column(Integer, nullable=False, default=0)


class CommerceOperationEvent(Base):
    """Operations log line: one turn, vote, handoff ticket, or approval-card action."""

    __tablename__ = "commerce_operation_events"

    id = Column(Integer, primary_key=True)
    role = Column(String(20), nullable=False)
    kind = Column(String(20), nullable=False)
    session_id = Column(String(64))
    turn_id = Column(String(40))
    ticket = Column(String(20))
    record_json = Column(JSON, nullable=False)
    resolved_at = Column(DateTime)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_commerce_operation_kind", "role", "kind", "created_at"),
        Index("idx_commerce_operation_session", "session_id", "created_at"),
        Index("idx_commerce_operation_turn", "turn_id"),
    )


class BuyerPortalInvite(Base):
    """Revocable access link a sales rep issues so a customer can use the buyer assistant."""

    __tablename__ = "buyer_portal_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_buyer_portal_invite_customer", "customer_id", "created_at"),
    )
