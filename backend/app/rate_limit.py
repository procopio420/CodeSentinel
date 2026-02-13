from typing import Optional
from redis.asyncio import Redis, from_url
from fastapi import Request
from .config import settings
import time
import ipaddress
import logging

logger = logging.getLogger(__name__)

_rate: Optional[Redis] = None


async def init_rate_limiter(url: Optional[str] = None):
    global _rate
    if _rate is None:
        _rate = from_url(url or settings.RATE_LIMIT_REDIS_URL, decode_responses=True)
    return _rate


async def get_rate_redis() -> Redis:
    global _rate
    if _rate is None:
        await init_rate_limiter()
    assert _rate is not None
    return _rate


async def close_rate_limiter():
    global _rate
    if _rate is not None:
        await _rate.aclose()
        _rate = None


def extract_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling X-Forwarded-For if trusted proxies are enabled.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client IP address as string
    """
    if settings.TRUSTED_PROXY_HEADERS:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
            # Take the first public IP in the list
            ips = [ip.strip() for ip in xff.split(",")]
            for ip_str in ips:
                try:
                    ip = ipaddress.ip_address(ip_str)
                    # Return first public IP (not private/localhost)
                    if not ip.is_private and not ip.is_loopback and not ip.is_link_local:
                        logger.debug(f"extracted_ip_from_xff ip={ip_str}")
                        return ip_str
                except ValueError:
                    continue
            # If no public IP found, use first one anyway (fallback)
            if ips:
                logger.debug(f"using_first_xff_ip ip={ips[0]}")
                return ips[0]
    
    # Default: use direct client host
    ip = request.client.host if request.client else "unknown"
    logger.debug(f"using_client_host ip={ip}")
    return ip


async def limit_check(ip: str, per_hour: Optional[int] = None):
    r = await get_rate_redis()
    limit = per_hour or int(settings.RATE_LIMIT_PER_HOUR)
    bucket = int(time.time() // 3600)
    key = f"ratelimit:{ip}:{bucket}"
    cnt = await r.incr(key)
    if cnt == 1:
        await r.expire(key, 3600)
    if cnt > limit:
        logger.warning(f"rate_limit_exceeded ip={ip} count={cnt} limit={limit}")
        from fastapi import HTTPException

        raise HTTPException(
            status_code=429, detail=f"Rate limit exceeded ({limit} reviews/hour)"
        )
    logger.debug(f"rate_limit_check ip={ip} count={cnt} limit={limit}")
