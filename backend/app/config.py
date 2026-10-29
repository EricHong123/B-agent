"""
Application configuration using Pydantic Settings
"""
from pathlib import Path
from typing import Dict, List, Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Trade AI Agent"
    APP_VERSION: str = "1.0.0"
    DEPLOYMENT_ENVIRONMENT: Literal[
        "development", "staging", "production"
    ] = "development"
    DEPLOYMENT_TENANCY: Literal["single_organization"] = "single_organization"
    DEPLOYMENT_ID: str = Field(default="local", min_length=1, max_length=100)
    DEBUG: bool = False
    SECRET_KEY: str = "your-secret-key-change-in-production"
    START_MINIMAL: bool = False
    AGENT_ORG_ID: UUID = UUID("ba6e0000-0000-0000-0000-000000000001")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./trade_ai.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_URL: str = "redis://localhost:6379/1"
    AGENT_RETRIEVAL_CACHE_ENABLED: bool = True
    AGENT_RETRIEVAL_CACHE_TTL_SECONDS: int = Field(default=60, ge=1, le=3600)
    AGENT_CONCURRENCY_GLOBAL_LIMIT: int = Field(default=32, ge=1, le=10000)
    AGENT_CONCURRENCY_ORG_LIMIT: int = Field(default=16, ge=1, le=10000)
    AGENT_CONCURRENCY_USER_LIMIT: int = Field(default=4, ge=1, le=10000)
    AGENT_CONCURRENCY_PROVIDER_LIMIT: int = Field(default=16, ge=1, le=10000)
    AGENT_CONCURRENCY_TOOL_LIMIT: int = Field(default=8, ge=1, le=10000)
    AGENT_CONCURRENCY_LEASE_SECONDS: int = Field(default=300, ge=1, le=3600)
    AGENT_FAST_PATH_ENABLED: bool = True
    AGENT_FAST_PATH_MAX_INPUT_CHARS: int = Field(default=240, ge=40, le=4000)
    AGENT_FAST_PATH_MAX_HISTORY_MESSAGES: int = Field(default=6, ge=1, le=20)
    AGENT_FAST_PATH_MAX_OUTPUT_TOKENS: int = Field(default=800, ge=256, le=1600)

    # Quotations above this total or below this margin need a second, admin approver.
    FULFILLMENT_QUOTE_APPROVAL_THRESHOLD: float = Field(default=50_000, ge=0)
    FULFILLMENT_QUOTE_MIN_MARGIN_PERCENT: float = Field(default=15, ge=0, le=100)
    FULFILLMENT_QUOTE_EXPIRY_WARNING_DAYS: int = Field(default=3, ge=0, le=90)

    # Media production remains fail-closed until each plane is explicitly enabled.
    MEDIA_UPLOAD_ENABLED: bool = False
    MEDIA_PLANNING_ENABLED: bool = False
    MEDIA_SUBMIT_ENABLED: bool = False
    MEDIA_SUBMIT_BATCH_SIZE: int = Field(default=5, ge=1, le=100)
    MEDIA_SUBMIT_LEASE_SECONDS: int = Field(default=300, ge=300, le=900)
    MEDIA_SUBMIT_POLL_SECONDS: int = Field(default=10, ge=1, le=900)
    MEDIA_JOB_DEADLINE_SECONDS: int = Field(default=3600, ge=60, le=86_400)
    MEDIA_T2V_RESERVATION_CEILING_MICROUSD: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000_000,
    )
    MEDIA_INTENT_VAULT_DIR: str = "./data/private/media-intents"
    MEDIA_INTENT_VAULT_KEY_FILE: str = "./data/secrets/media-intent.key"
    MEDIA_POLICY_VERSION: str = Field(default="media-policy-v1", min_length=1)
    MEDIA_POLICY_SIGNING_KEY: str = ""
    MEDIA_POLICY_DECISION_TTL_SECONDS: int = Field(default=120, ge=1, le=900)
    MEDIA_OBJECT_STORE_BACKEND: Literal["local", "s3"] = "local"
    MEDIA_S3_ENDPOINT_URL: str = ""
    MEDIA_S3_REGION: str = "us-east-1"
    MEDIA_S3_QUARANTINE_BUCKET: str = ""
    MEDIA_S3_ASSET_BUCKET: str = ""
    MEDIA_S3_KEY_PREFIX: str = ""
    MEDIA_S3_KMS_KEY_ID: str = ""
    MEDIA_DOWNLOAD_TTL_SECONDS: int = Field(default=120, ge=30, le=300)
    MEDIA_PROVIDER_INPUT_TTL_SECONDS: int = Field(
        default=3600,
        ge=300,
        le=86_400,
    )
    MEDIA_THUMBNAIL_ENABLED: bool = False
    MEDIA_FFMPEG_PATH: str = "/usr/bin/ffmpeg"
    MEDIA_THUMBNAIL_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=300)
    MEDIA_THUMBNAIL_PROCESS_OUTPUT_BYTES: int = Field(
        default=1_048_576,
        ge=1024,
        le=16_777_216,
    )
    MEDIA_THUMBNAIL_MAX_BYTES: int = Field(
        default=10_485_760,
        ge=1024,
        le=52_428_800,
    )
    MEDIA_LIFECYCLE_ENABLED: bool = False
    MEDIA_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    MEDIA_CLEANUP_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    MEDIA_MAINTENANCE_USER_ID: int = Field(default=1, ge=1)
    MEDIA_INSPECTION_ENABLED: bool = False
    MEDIA_CLAMSCAN_PATH: str = "/usr/bin/clamscan"
    MEDIA_FFPROBE_PATH: str = "/usr/bin/ffprobe"
    MEDIA_INSPECTION_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=300)
    MEDIA_INSPECTION_MAX_OUTPUT_BYTES: int = Field(
        default=1_048_576,
        ge=1024,
        le=16_777_216,
    )
    MEDIA_MAX_DURATION_SECONDS: int = Field(default=600, ge=1, le=86_400)
    MEDIA_MAX_DIMENSION_PIXELS: int = Field(default=8192, ge=64, le=32_768)
    MEDIA_RUNTIME_SECRET_DIR: str = "./data/secrets/media-runtime"
    MEDIA_RESULT_MAX_BYTES: int = Field(
        default=1_073_741_824,
        ge=1024,
        le=2_147_483_648,
    )
    MEDIA_RESULT_DOWNLOAD_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        gt=0,
        le=300,
    )
    MEDIA_RECONCILE_BATCH_SIZE: int = Field(default=10, ge=1, le=100)
    MEDIA_RECONCILE_LEASE_SECONDS: int = Field(default=300, ge=300, le=900)
    MEDIA_RECONCILE_POLL_SECONDS: int = Field(default=15, ge=1, le=900)
    MEDIA_RECONCILE_RETRY_SECONDS: int = Field(default=30, ge=1, le=3600)
    MEDIA_CALLBACK_ENABLED: bool = False
    MEDIA_CALLBACK_MAX_BODY_BYTES: int = Field(
        default=262_144,
        ge=1024,
        le=1_048_576,
    )
    MEDIA_FAL_WEBHOOK_USER_ID: str = Field(default="", max_length=255)
    MEDIA_FAL_WEBHOOK_URL: str = Field(default="", max_length=2000)
    MEDIA_FAL_JWKS_CACHE_SECONDS: int = Field(
        default=3600,
        ge=60,
        le=86_400,
    )
    MEDIA_FAL_JWKS_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=15)

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/2"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/3"

    # AI Provider
    AI_PROVIDER: str = "tongyi"  # tongyi, qwen, openai
    TONGYI_API_KEY: str = ""
    TONGYI_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""

    # Internal LLM Gateway (disabled until explicitly enabled)
    LLM_BACKEND: Literal["direct", "omniroute"] = "direct"
    OMNIROUTE_BASE_URL: str = "http://omniroute:20128"
    OMNIROUTE_API_KEY: str = ""
    OMNIROUTE_API_KEY_FILE: str = ""
    AI_RUNTIME_SECRET_FILE: str = "./data/secrets/omniroute_api_key"
    CONNECTOR_SECRET_DIR: str = "./data/secrets/connectors"
    MAILBOX_SECRET_DIR: str = "./data/secrets/mailboxes"
    OMNIROUTE_ALLOWED_PROVIDERS: List[str] = []
    OMNIROUTE_TIMEOUT_SECONDS: float = 60.0
    OMNIROUTE_MODEL_LEAD_CLASSIFICATION: str = ""
    OMNIROUTE_MODEL_MESSAGE_DRAFT: str = ""
    OMNIROUTE_MODEL_LIVE_REPLY: str = ""
    OMNIROUTE_MODEL_RAG_QUERY_REWRITE: str = ""
    OMNIROUTE_MODEL_SUMMARIZATION: str = ""

    # Email Service
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    # Gmail API
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/api/v1/mailboxes/oauth/callback/gmail"

    # Outlook API
    OUTLOOK_CLIENT_ID: str = ""
    OUTLOOK_CLIENT_SECRET: str = ""
    OUTLOOK_REDIRECT_URI: str = "http://localhost:8000/api/v1/mailboxes/oauth/callback/outlook"
    OUTLOOK_TENANT_ID: str = "common"

    # Browser origin used after a server-side mailbox OAuth callback.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # WhatsApp
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = ""

    # Data Service APIs
    APIFY_API_KEY: str = ""
    BRIGHT_DATA_API_KEY: str = ""
    ZYTE_API_KEY: str = ""

    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS: str = ""

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Rate Limiting
    EMAIL_RATE_LIMIT: int = 100  # emails per hour per account
    WHATSAPP_RATE_LIMIT: int = 60  # messages per hour

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    EXPORT_DIR: str = "./exports"
    TEMPLATE_DIR: str = "./app/templates"
    CHROMA_DB_DIR: str = "./chroma_db"

    # Monitoring
    ENABLE_METRICS: bool = True
    PROMETHEUS_PORT: int = 9090

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    @field_validator(
        "OMNIROUTE_MODEL_LEAD_CLASSIFICATION",
        "OMNIROUTE_MODEL_MESSAGE_DRAFT",
        "OMNIROUTE_MODEL_LIVE_REPLY",
        "OMNIROUTE_MODEL_RAG_QUERY_REWRITE",
        "OMNIROUTE_MODEL_SUMMARIZATION",
    )
    @classmethod
    def reject_dynamic_gateway_routes(cls, value: str) -> str:
        value = value.strip()
        if value.lower().startswith("auto/"):
            raise ValueError("dynamic auto/* routes are not approved")
        return value

    @field_validator("OMNIROUTE_ALLOWED_PROVIDERS")
    @classmethod
    def normalize_gateway_provider_allowlist(cls, values: List[str]) -> List[str]:
        providers = []
        for value in values:
            provider = value.strip().lower()
            if provider and provider not in providers:
                providers.append(provider)
        return providers

    def omniroute_model_aliases(self) -> Dict[str, str]:
        aliases = {
            "lead_classification": self.OMNIROUTE_MODEL_LEAD_CLASSIFICATION,
            "message_draft": self.OMNIROUTE_MODEL_MESSAGE_DRAFT,
            "live_reply": self.OMNIROUTE_MODEL_LIVE_REPLY,
            "rag_query_rewrite": self.OMNIROUTE_MODEL_RAG_QUERY_REWRITE,
            "summarization": self.OMNIROUTE_MODEL_SUMMARIZATION,
        }
        return {use_case: alias for use_case, alias in aliases.items() if alias}

    @model_validator(mode="after")
    def validate_media_feature_dependencies(self) -> "Settings":
        if (
            self.DEPLOYMENT_ENVIRONMENT == "production"
            and self.MEDIA_UPLOAD_ENABLED
            and self.MEDIA_OBJECT_STORE_BACKEND != "s3"
        ):
            raise ValueError("production media uploads require the S3 backend")
        media_storage_enabled = any(
            (
                self.MEDIA_UPLOAD_ENABLED,
                self.MEDIA_INSPECTION_ENABLED,
                self.MEDIA_THUMBNAIL_ENABLED,
                self.MEDIA_LIFECYCLE_ENABLED,
            )
        )
        if media_storage_enabled and self.MEDIA_OBJECT_STORE_BACKEND == "s3":
            if (
                not self.MEDIA_S3_QUARANTINE_BUCKET
                or not self.MEDIA_S3_ASSET_BUCKET
            ):
                raise ValueError("S3 media processing requires both media buckets")
            if self.MEDIA_S3_QUARANTINE_BUCKET == self.MEDIA_S3_ASSET_BUCKET:
                raise ValueError("S3 quarantine and asset buckets must differ")
        if self.MEDIA_INSPECTION_ENABLED:
            if self.MEDIA_OBJECT_STORE_BACKEND != "s3":
                raise ValueError("media inspection requires the S3 backend")
            if not Path(self.MEDIA_CLAMSCAN_PATH).is_absolute():
                raise ValueError("MEDIA_CLAMSCAN_PATH must be absolute")
            if not Path(self.MEDIA_FFPROBE_PATH).is_absolute():
                raise ValueError("MEDIA_FFPROBE_PATH must be absolute")
        if self.MEDIA_THUMBNAIL_ENABLED:
            if self.MEDIA_OBJECT_STORE_BACKEND != "s3":
                raise ValueError("media thumbnails require the S3 backend")
            if not Path(self.MEDIA_FFMPEG_PATH).is_absolute():
                raise ValueError("MEDIA_FFMPEG_PATH must be absolute")
        if (
            self.MEDIA_LIFECYCLE_ENABLED
            and self.MEDIA_OBJECT_STORE_BACKEND != "s3"
        ):
            raise ValueError("media lifecycle cleanup requires the S3 backend")
        if (
            self.DEPLOYMENT_ENVIRONMENT == "production"
            and self.MEDIA_UPLOAD_ENABLED
            and not self.MEDIA_INSPECTION_ENABLED
        ):
            raise ValueError("production media uploads require inspection")
        if self.MEDIA_SUBMIT_ENABLED and (
            not self.MEDIA_UPLOAD_ENABLED
            or not self.MEDIA_INSPECTION_ENABLED
            or not self.MEDIA_PLANNING_ENABLED
        ):
            raise ValueError(
                "media submission requires upload, inspection, and planning"
            )
        if (
            self.MEDIA_SUBMIT_ENABLED
            and len(self.MEDIA_POLICY_SIGNING_KEY) < 32
        ):
            raise ValueError(
                "media submission requires a dedicated signing key of at least 32 characters"
            )
        if self.MEDIA_SUBMIT_ENABLED and (
            not Path(self.MEDIA_INTENT_VAULT_DIR).is_absolute()
            or not Path(self.MEDIA_INTENT_VAULT_KEY_FILE).is_absolute()
        ):
            raise ValueError(
                "media submission requires absolute private intent vault paths"
            )
        if (
            self.MEDIA_SUBMIT_ENABLED
            and self.MEDIA_T2V_RESERVATION_CEILING_MICROUSD <= 0
        ):
            raise ValueError(
                "media submission requires a positive T2V reservation ceiling"
            )
        if (
            self.MEDIA_SUBMIT_ENABLED
            and self.MEDIA_PROVIDER_INPUT_TTL_SECONDS
            < self.MEDIA_JOB_DEADLINE_SECONDS
        ):
            raise ValueError(
                "media provider input credential lifetime must cover the job deadline"
            )
        if (
            self.MEDIA_CALLBACK_ENABLED
            and not self.MEDIA_FAL_WEBHOOK_USER_ID.strip()
        ):
            raise ValueError(
                "media callbacks require the expected Fal webhook user ID"
            )
        if self.MEDIA_CALLBACK_ENABLED:
            callback_url = urlsplit(self.MEDIA_FAL_WEBHOOK_URL)
            if (
                callback_url.scheme != "https"
                or not callback_url.hostname
                or callback_url.username is not None
                or callback_url.password is not None
                or callback_url.query
                or callback_url.fragment
            ):
                raise ValueError(
                    "media callbacks require a safe HTTPS webhook URL"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
