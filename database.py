"""PostgreSQL connection and migration support for the future AI agent.

This module is intentionally not imported by ``bot.py`` yet. The existing
ticket and showcase bot therefore keeps its current behaviour until the AI
agent is added in step 3.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")
DEFAULT_CONNECT_RETRIES = 10


class DatabaseConfigurationError(RuntimeError):
    """Raised when database setup is requested without a connection string."""


async def create_pool(database_url: str) -> asyncpg.Pool:
    """Create a small pool suitable for one Discord bot process."""

    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )


async def create_pool_with_retry(
    database_url: str,
    retries: int = DEFAULT_CONNECT_RETRIES,
) -> asyncpg.Pool:
    """Wait briefly for Railway Postgres during a first deployment."""

    for attempt in range(1, retries + 1):
        try:
            return await create_pool(database_url)
        except (OSError, asyncpg.PostgresError):
            if attempt == retries:
                raise
            await asyncio.sleep(min(2**(attempt - 1), 15))

    raise RuntimeError("Database retry loop ended unexpectedly.")


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIRECTORY.glob("[0-9][0-9][0-9]_*.sql"))


async def apply_migrations(pool: asyncpg.Pool) -> None:
    """Apply each numbered SQL migration exactly once."""

    async with pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        for migration in _migration_files():
            version = migration.name.split("_", maxsplit=1)[0]
            already_applied = await connection.fetchval(
                "SELECT 1 FROM schema_migrations WHERE version = $1", version
            )
            if already_applied:
                continue

            sql = migration.read_text(encoding="utf-8")
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )


async def migrate_from_environment() -> None:
    """Run migrations using DATABASE_URL; used by Railway before deployment."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is required for migrations.")

    pool = await create_pool_with_retry(database_url)
    try:
        await apply_migrations(pool)
    finally:
        await pool.close()


def main() -> None:
    command = sys.argv[1:]
    if command != ["migrate"]:
        raise SystemExit("Usage: python -m database migrate")
    asyncio.run(migrate_from_environment())


if __name__ == "__main__":
    main()
