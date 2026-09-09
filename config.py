"""Central configuration for the Discord bot.

Secrets are deliberately read from environment variables only. This module
does not initialise an OpenAI client and is safe to use before the AI feature.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Railway already injects variables into the process. Locally, this loads a
# developer-owned .env file without ever placing secrets in source control.
load_dotenv()


class ConfigurationError(ValueError):
    """Raised when an environment variable has an invalid value."""


def _read_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false.")


def _read_positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        number = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a whole number.") from error
    if number < 1:
        raise ConfigurationError(f"{name} must be at least 1.")
    return number


@dataclass(frozen=True)
class Settings:
    """Validated configuration shared by later bot modules."""

    discord_bot_token: str | None
    database_url: str | None
    ai_enabled: bool
    openai_api_key: str | None
    openai_model: str
    ai_max_input_characters: int
    ai_max_output_tokens: int
    ai_request_timeout_seconds: int
    ai_max_concurrent_requests: int
    ai_user_cooldown_seconds: int
    ai_daily_user_limit: int
    ai_daily_guild_limit: int
    ai_context_message_limit: int
    ai_message_retention_days: int
    ai_memory_retention_days: int
    ai_memory_max_items: int
    ai_memory_max_characters: int

    @property
    def missing_startup_secret(self) -> str | None:
        if not self.discord_bot_token:
            return "DISCORD_BOT_TOKEN"
        if self.ai_enabled and not self.openai_api_key:
            return "OPENAI_API_KEY"
        if self.ai_enabled and not self.database_url:
            return "DATABASE_URL"
        return None


def get_settings() -> Settings:
    """Read and validate environment variables without exposing secret values."""

    return Settings(
        discord_bot_token=os.getenv("DISCORD_BOT_TOKEN"),
        database_url=os.getenv("DATABASE_URL"),
        ai_enabled=_read_bool("AI_ENABLED", default=False),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        ai_max_input_characters=_read_positive_int("AI_MAX_INPUT_CHARACTERS", 2_000),
        ai_max_output_tokens=_read_positive_int("AI_MAX_OUTPUT_TOKENS", 600),
        ai_request_timeout_seconds=_read_positive_int(
            "AI_REQUEST_TIMEOUT_SECONDS", 30
        ),
        ai_max_concurrent_requests=_read_positive_int(
            "AI_MAX_CONCURRENT_REQUESTS", 3
        ),
        ai_user_cooldown_seconds=_read_positive_int("AI_USER_COOLDOWN_SECONDS", 10),
        ai_daily_user_limit=_read_positive_int("AI_DAILY_USER_LIMIT", 30),
        ai_daily_guild_limit=_read_positive_int("AI_DAILY_GUILD_LIMIT", 500),
        ai_context_message_limit=_read_positive_int("AI_CONTEXT_MESSAGE_LIMIT", 8),
        ai_message_retention_days=_read_positive_int("AI_MESSAGE_RETENTION_DAYS", 30),
        ai_memory_retention_days=_read_positive_int("AI_MEMORY_RETENTION_DAYS", 180),
        ai_memory_max_items=_read_positive_int("AI_MEMORY_MAX_ITEMS", 10),
        ai_memory_max_characters=_read_positive_int("AI_MEMORY_MAX_CHARACTERS", 500),
    )
