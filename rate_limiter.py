"""
rate_limiter.py
Production in-memory sliding-window rate limiter for FastAPI:
- Protects upload endpoints, AI chat endpoint, and cleanup endpoint
- Identifies client by X-Forwarded-For (reverse proxy) or socket IP
- Returns HTTP 429 Too Many Requests with Retry-After header
- Configurable limits via environment variables
"""

import os
import threading
import time
from typing import Dict, List
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window in-memory rate limiter."""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self.lock = threading.Lock()
        self.history: Dict[str, List[float]] = {}

    def is_allowed(self, key: str, max_requests: int) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        with self.lock:
            timestamps = self.history.get(key, [])
            recent = [ts for ts in timestamps if ts > cutoff]
            if len(recent) >= max_requests:
                self.history[key] = recent
                return False
            recent.append(now)
            self.history[key] = recent
            return True

    def get_retry_after(self, key: str, max_requests: int) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        with self.lock:
            timestamps = self.history.get(key, [])
            recent = [ts for ts in timestamps if ts > cutoff]
            if not recent:
                return 1
            return max(1, int(self.window_seconds - (now - recent[0])))

    def reset(self) -> None:
        with self.lock:
            self.history.clear()


_global_limiter = SlidingWindowRateLimiter(window_seconds=60.0)


def is_rate_limit_enabled() -> bool:
    """Check if rate limiting is enabled in environment."""
    val = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower()
    return val in ("true", "1", "yes", "enabled")


def get_limit_for_bucket(bucket: str) -> int:
    """Read configured request limit per minute for a specific bucket."""
    env_vars = {
        "upload": "RATE_LIMIT_UPLOAD_PER_MINUTE",
        "ai_chat": "RATE_LIMIT_AI_CHAT_PER_MINUTE",
        "cleanup": "RATE_LIMIT_CLEANUP_PER_MINUTE",
    }
    defaults = {
        "upload": 60,
        "ai_chat": 30,
        "cleanup": 10,
    }
    env_name = env_vars.get(bucket, "RATE_LIMIT_UPLOAD_PER_MINUTE")
    default_val = defaults.get(bucket, 60)
    try:
        val = int(os.getenv(env_name, str(default_val)).strip())
        return max(1, val)
    except Exception:
        return default_val


def get_client_ip(request: Request) -> str:
    """Extract client IP address from proxy headers or socket connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in comma-separated list is the original client
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host.strip()
    return "127.0.0.1"


def check_rate_limit(request: Request, bucket: str) -> None:
    """
    Check if the client has exceeded the rate limit for the specified bucket.
    Raises HTTPException(429) if exceeded.
    """
    if not is_rate_limit_enabled():
        return

    client_ip = get_client_ip(request)
    limit = get_limit_for_bucket(bucket)
    key = f"{bucket}:{client_ip}"

    if not _global_limiter.is_allowed(key, limit):
        retry_after = _global_limiter.get_retry_after(key, limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {bucket}. Max {limit} requests per minute. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


async def rate_limit_upload(request: Request) -> None:
    """FastAPI dependency for document upload endpoints."""
    check_rate_limit(request, "upload")


async def rate_limit_ai_chat(request: Request) -> None:
    """FastAPI dependency for AI chat questions endpoint."""
    check_rate_limit(request, "ai_chat")


async def rate_limit_cleanup(request: Request) -> None:
    """FastAPI dependency for document storage cleanup endpoint."""
    check_rate_limit(request, "cleanup")


def reset_rate_limits() -> None:
    """Helper to clear in-memory rate limiting state (useful for tests)."""
    _global_limiter.reset()
