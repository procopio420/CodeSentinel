from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from .config import settings
from .routes import reviews, stats, health
from .db import init_db, close_db
from .cache import init_cache, close_cache
from .rate_limit import init_rate_limiter, close_rate_limiter
from .events import init_events, close_events


def origin_from_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_cache()
    await init_rate_limiter()
    await init_events()
    try:
        yield
    finally:
        await close_events()
        await close_rate_limiter()
        await close_cache()
        await close_db()


app = FastAPI(title="AI Code Review", version="0.1.0", lifespan=lifespan)

origins = {
    origin_from_url(getattr(settings, "FRONTEND_URL", "http://localhost:5173")),
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Location"],
)
app.include_router(health.router)
app.include_router(reviews.router)
app.include_router(stats.router)
