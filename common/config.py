"""
Centralised configuration via Pydantic Settings.

All environment variables consumed by momentum-ops are declared here as a
single source of truth.  Values can be set via ``.env`` files, actual
environment variables, or Docker Compose ``environment:`` blocks — Pydantic
Settings handles all three transparently.

Usage
-----
>>> from shared.config import settings
>>> print(settings.db_url)
'postgresql://momentum_user:momentum_password@localhost:5432/momentum_db'
"""

from __future__ import annotations

import socket
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # silently ignore unexpected env vars
        case_sensitive=False,    # DB_HOST == db_host
    )

    
    env_type: str = socket.gethostname().split('-')[-1]

    # ── PostgreSQL ────────────────────────────────────────────────────────
    # db_host: str = Field(default="localhost", description="Postgres hostname")
    # db_port: int = Field(default=5432, description="Postgres port")
    # db_name_base: str = Field(default="momentum_db", description="Base Postgres database name")
    # db_user: str = Field(default="momentum_user", description="Postgres user")
    # db_password: str = Field(default="momentum_password", description="Postgres password")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_name(self) -> str:
        """Return the environment-specific database name."""
        suffix = '_prod' if self.env_type == 'prod' else '_stg'
        return f"{self.db_name_base}{suffix}"

    # ── Computed DSN (read-only) ──────────────────────────────────────────
    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_url(self) -> str:
        """Construct a full ``postgresql://`` DSN from individual components."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── API keys (optional — populated when needed) ───────────────────────
    fmp_api_key: str | None = Field(
        default=None, description="Financial Modeling Prep API key"
    )
    openai_api_key: str | None = Field(
        default=None, description="OpenAI API key for advisory features"
    )

    # ── Application behaviour ─────────────────────────────────────────────
    default_ticker: str = Field(
        default="AAPL", description="Fallback ticker when none is specified"
    )
    model_artifacts_dir: str = Field(
        default="model_artifacts",
        description="Path to the directory containing trained XGBoost JSON artefacts",
    )
    min_history_rows: int = Field(
        default=200,
        ge=60,
        description="Minimum daily rows required for reliable feature engineering",
    )

    # ── KIS (Korea Investment & Securities) ────────────────────────────────
    kis_app_key: str | None = Field(
        default=None, description="KIS Open API application key"
    )
    kis_app_secret: str | None = Field(
        default=None, description="KIS Open API application secret"
    )
    kis_api_base_url: str = Field(
        default="https://openapi.koreainvestment.com:9443",
        description="KIS Open API base URL",
    )
    kis_token_path: str = Field(
        default="ephemeral/token.json",
        description="File path where the KIS access token JSON is saved",
    )

    # ── Prefect ───────────────────────────────────────────────────────────
    prefect_api_url: str | None = Field(
        default=None, description="Prefect API endpoint (e.g. http://prefect:4200/api)"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of application settings."""
    return Settings()


# Convenience alias for direct imports:  ``from shared.config import settings``
settings: Settings = get_settings()


# ── yfinance symbol mapping ───────────────────────────────────────────────────

# Region → yfinance suffix.  US tickers have no suffix.
_YF_SUFFIX: dict[str, str] = {
    "KR": ".KS",
    "JP": ".T",
    "US": "",
    "GLOBAL": "",
}


def to_yf_symbol(symbol: str, region: str) -> str:
    """Convert a stored (symbol, region) pair to a yfinance-compatible ticker.

    Examples
    --------
    >>> to_yf_symbol("069500", "KR")
    '069500.KS'
    >>> to_yf_symbol("AAPL", "US")
    'AAPL'
    >>> to_yf_symbol("7203", "JP")
    '7203.T'
    """
    suffix = _YF_SUFFIX.get(region.upper(), "")
    # If the symbol already contains the suffix, don't double-append.
    if suffix and not symbol.upper().endswith(suffix):
        return f"{symbol}{suffix}"
    return symbol