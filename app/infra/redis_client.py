import os
import redis


def get_redis_client():
    """
    Returns a Redis client configured with safe timeouts.
    Does NOT raise on connection failure.
    """

    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))

    try:
        client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
            socket_connect_timeout=1,   # short connect timeout
            socket_timeout=1,           # short operation timeout
        )

        # Lightweight ping to verify connectivity
        client.ping()
        return client

    except Exception:
        # Fail-open behavior: return None if Redis unavailable
        return None