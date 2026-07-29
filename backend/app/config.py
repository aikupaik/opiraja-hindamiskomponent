"""Validated environment configuration for the assessment API."""

from typing import Annotated

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class Settings(BaseSettings):
    """Application settings with no implicit credentials or service locations."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="forbid",
        populate_by_name=True,
        validate_default=True,
    )

    supabase_url: AnyHttpUrl = Field(
        validation_alias=AliasChoices("SUPABASE_URL", "supabase_url")
    )
    supabase_service_key: SecretStr = Field(
        min_length=1,
        validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "supabase_service_key"),
    )
    r_service_url: AnyHttpUrl = Field(
        validation_alias=AliasChoices("R_SERVICE_URL", "r_service_url")
    )
    admin_access_key: SecretStr | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("ADMIN_ACCESS_KEY", "admin_access_key"),
    )

    max_graph_nodes: PositiveInt = Field(
        default=10,
        validation_alias=AliasChoices("MAX_GRAPH_NODES", "max_graph_nodes"),
    )
    r_max_connections: PositiveInt = Field(
        default=4,
        validation_alias=AliasChoices("R_MAX_CONNECTIONS", "r_max_connections"),
    )
    r_connect_timeout_seconds: PositiveFloat = Field(
        default=2.0,
        validation_alias=AliasChoices(
            "R_CONNECT_TIMEOUT_SECONDS", "r_connect_timeout_seconds"
        ),
    )
    r_read_timeout_seconds: PositiveFloat = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "R_READ_TIMEOUT_SECONDS", "r_read_timeout_seconds"
        ),
    )
    r_write_timeout_seconds: PositiveFloat = Field(
        default=5.0,
        validation_alias=AliasChoices(
            "R_WRITE_TIMEOUT_SECONDS", "r_write_timeout_seconds"
        ),
    )
    r_pool_timeout_seconds: PositiveFloat = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "R_POOL_TIMEOUT_SECONDS", "r_pool_timeout_seconds"
        ),
    )
    readiness_timeout_seconds: PositiveFloat = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "READINESS_TIMEOUT_SECONDS", "readiness_timeout_seconds"
        ),
    )
    supabase_request_timeout_seconds: PositiveFloat = Field(
        default=10.0,
        validation_alias=AliasChoices(
            "SUPABASE_REQUEST_TIMEOUT_SECONDS",
            "supabase_request_timeout_seconds",
        ),
    )
    admin_source_max_bytes: PositiveInt = Field(
        default=10_000_000,
        validation_alias=AliasChoices(
            "ADMIN_SOURCE_MAX_BYTES", "admin_source_max_bytes"
        ),
    )
    admin_source_max_pdf_pages: PositiveInt = Field(
        default=100,
        validation_alias=AliasChoices(
            "ADMIN_SOURCE_MAX_PDF_PAGES", "admin_source_max_pdf_pages"
        ),
    )
    admin_source_max_text_chars: PositiveInt = Field(
        default=1_000_000,
        validation_alias=AliasChoices(
            "ADMIN_SOURCE_MAX_TEXT_CHARS", "admin_source_max_text_chars"
        ),
    )
    admin_source_max_redirects: Annotated[int, Field(ge=0, le=20)] = Field(
        default=5,
        validation_alias=AliasChoices(
            "ADMIN_SOURCE_MAX_REDIRECTS", "admin_source_max_redirects"
        ),
    )
    admin_source_fetch_timeout_seconds: PositiveFloat = Field(
        default=10.0,
        validation_alias=AliasChoices(
            "ADMIN_SOURCE_FETCH_TIMEOUT_SECONDS",
            "admin_source_fetch_timeout_seconds",
        ),
    )
    admin_diagnostic_max_events: PositiveInt = Field(
        default=500,
        validation_alias=AliasChoices(
            "ADMIN_DIAGNOSTIC_MAX_EVENTS", "admin_diagnostic_max_events"
        ),
    )
    admin_diagnostic_ttl_seconds: PositiveInt = Field(
        default=3600,
        validation_alias=AliasChoices(
            "ADMIN_DIAGNOSTIC_TTL_SECONDS", "admin_diagnostic_ttl_seconds"
        ),
    )
