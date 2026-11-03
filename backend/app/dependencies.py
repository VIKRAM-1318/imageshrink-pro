from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis_client import get_redis


async def get_session(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[AsyncSession, None]:
    """Alias dependency for database sessions."""
    yield session


async def get_redis_client(
    request: Request,
) -> aioredis.Redis:
    """Dependency that returns the shared Redis client."""
    return await get_redis()
