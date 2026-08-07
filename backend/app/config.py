"""Validated environment configuration for the assessment API."""

from typing import Annotated

from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


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
    allowed_hosts: list[str] = Field(
        min_length=1,
        validation_alias=AliasChoices("ALLOWED_HOSTS", "allowed_hosts"),
    )
    admin_access_key: SecretStr | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("ADMIN_ACCESS_KEY", "admin_access_key"),
    )
    or_jwt_secret: SecretStr = Field(
        min_length=32,
        validation_alias=AliasChoices("OR_JWT_SECRET", "or_jwt_secret"),
    )
    api_jwt_secret: SecretStr = Field(
        min_length=32,
        validation_alias=AliasChoices("API_JWT_SECRET", "api_jwt_secret"),
    )
    or_jwt_issuer: str = Field(
        min_length=1,
        validation_alias=AliasChoices("OR_JWT_ISSUER", "or_jwt_issuer"),
    )
    player_app_url: str = Field(
        validation_alias=AliasChoices("PLAYER_APP_URL", "player_app_url"),
    )
    or_jwt_max_lifetime_seconds: PositiveInt = Field(
        default=300,
        validation_alias=AliasChoices(
            "OR_JWT_MAX_LIFETIME_SECONDS", "or_jwt_max_lifetime_seconds"
        ),
    )
    player_jwt_lifetime_seconds: PositiveInt = Field(
        default=28_800,
        validation_alias=AliasChoices(
            "PLAYER_JWT_LIFETIME_SECONDS", "player_jwt_lifetime_seconds"
        ),
    )
    admin_jwt_lifetime_seconds: PositiveInt = Field(
        default=28_800,
        validation_alias=AliasChoices(
            "ADMIN_JWT_LIFETIME_SECONDS", "admin_jwt_lifetime_seconds"
        ),
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

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, hosts: list[str]) -> list[str]:
        normalized_hosts = [host.strip() for host in hosts]
        if any(not host for host in normalized_hosts):
            raise ValueError("ALLOWED_HOSTS must not contain empty hosts")
        if any("*" in host for host in normalized_hosts):
            raise ValueError("ALLOWED_HOSTS must contain exact hosts only")
        return normalized_hosts

    @field_validator("or_jwt_issuer")
    @classmethod
    def validate_or_jwt_issuer(cls, issuer: str) -> str:
        if not issuer.strip():
            raise ValueError("OR_JWT_ISSUER must not be blank")
        return issuer

    @field_validator("player_app_url")
    @classmethod
    def validate_player_app_url(cls, value: str) -> str:
        if "?" in value or "#" in value:
            raise ValueError("PLAYER_APP_URL must not contain a query or fragment")
        try:
            validated_url = _HTTP_URL_ADAPTER.validate_python(value)
            parsed = urlsplit(str(validated_url))
            port = parsed.port
        except ValueError as error:
            raise ValueError("PLAYER_APP_URL must be a valid absolute origin") from error
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("PLAYER_APP_URL must be an absolute HTTP(S) origin")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("PLAYER_APP_URL must not contain user information")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("PLAYER_APP_URL must contain only an origin")
        hostname = parsed.hostname
        if hostname is None:
            raise ValueError("PLAYER_APP_URL must contain a host")
        if parsed.scheme == "http" and hostname.casefold() not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("PLAYER_APP_URL requires HTTPS outside local development")
        netloc = parsed.netloc
        if port is not None and not netloc.endswith(f":{port}"):
            raise ValueError("PLAYER_APP_URL contains an invalid port")
        return urlunsplit((parsed.scheme, netloc, "", "", ""))

    @model_validator(mode="after")
    def validate_distinct_jwt_secrets(self) -> "Settings":
        if secrets_equal(self.or_jwt_secret, self.api_jwt_secret):
            raise ValueError("OR_JWT_SECRET and API_JWT_SECRET must differ")
        return self


def secrets_equal(first: SecretStr, second: SecretStr) -> bool:
    return first.get_secret_value() == second.get_secret_value()
