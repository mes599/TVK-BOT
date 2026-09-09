"""PostgreSQL-backed short-term context and opt-in long-term memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from config import Settings


@dataclass(frozen=True)
class ContextItem:
    role: str
    content: str


@dataclass(frozen=True)
class StoredMemory:
    id: int
    content: str
    expires_at: datetime | None


class MemoryStore:
    """Stores only limited context and user-requested durable information."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self.pool = pool
        self.settings = settings

    async def load_context(self, guild_id: int, channel_id: int, user_id: int) -> list[ContextItem]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT role, content FROM conversation_messages
                WHERE session_id = (
                    SELECT id FROM conversation_sessions
                    WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3
                ) AND expires_at > NOW()
                ORDER BY created_at DESC LIMIT $4
                """,
                guild_id, channel_id, user_id, self.settings.ai_context_message_limit,
            )
        return [ContextItem(row["role"], row["content"]) for row in reversed(rows)]

    async def load_memories(self, guild_id: int, user_id: int) -> list[StoredMemory]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, content, expires_at FROM memories
                WHERE guild_id = $1 AND user_id = $2
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC LIMIT $3
                """,
                guild_id, user_id, self.settings.ai_memory_max_items,
            )
        return [StoredMemory(row["id"], row["content"], row["expires_at"]) for row in rows]

    async def save_exchange(self, guild_id: int, channel_id: int, user_id: int, user_message: str, assistant_message: str) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.ai_message_retention_days)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                session_id = await connection.fetchval(
                    """
                    INSERT INTO conversation_sessions (guild_id, channel_id, user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, channel_id, user_id)
                    DO UPDATE SET updated_at = NOW() RETURNING id
                    """,
                    guild_id, channel_id, user_id,
                )
                await connection.executemany(
                    "INSERT INTO conversation_messages (session_id, role, content, expires_at) VALUES ($1, $2, $3, $4)",
                    [(session_id, "user", user_message, expires_at), (session_id, "assistant", assistant_message, expires_at)],
                )

    async def remember(self, guild_id: int, user_id: int, content: str) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.ai_memory_retention_days)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "INSERT INTO memories (guild_id, user_id, content, expires_at) VALUES ($1, $2, $3, $4)",
                    guild_id, user_id, content, expires_at,
                )
                await connection.execute(
                    """
                    DELETE FROM memories WHERE id IN (
                        SELECT id FROM memories WHERE guild_id = $1 AND user_id = $2
                        ORDER BY created_at DESC, id DESC OFFSET $3
                    )
                    """,
                    guild_id, user_id, self.settings.ai_memory_max_items,
                )

    async def reset_context(self, guild_id: int, channel_id: int, user_id: int) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM conversation_sessions WHERE guild_id = $1 AND channel_id = $2 AND user_id = $3",
                guild_id, channel_id, user_id,
            )

    async def forget_memories(self, guild_id: int, user_id: int) -> int:
        async with self.pool.acquire() as connection:
            result = await connection.execute(
                "DELETE FROM memories WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
            )
        return int(result.rsplit(" ", maxsplit=1)[-1])

    async def cleanup_expired(self) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM conversation_messages WHERE expires_at <= NOW()")
                await connection.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= NOW()")
                await connection.execute(
                    """
                    DELETE FROM conversation_sessions WHERE NOT EXISTS (
                        SELECT 1 FROM conversation_messages
                        WHERE conversation_messages.session_id = conversation_sessions.id
                    )
                    """
                )
