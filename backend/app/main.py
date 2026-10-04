import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from .config import settings
from .database import engine
from .maintenance import cleanup_loop
from .routers import accounts, assessments, teams


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


# Interactive API docs and the schema are only served where explicitly enabled (local development).
docs = {} if settings.api_docs_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="Player Skill Assessment API", redirect_slashes=False, lifespan=lifespan, **docs)
app.include_router(accounts.router)
app.include_router(teams.router)
app.include_router(assessments.router)


@app.middleware("http")
async def protect_origin(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            allowed = urlsplit(settings.public_base_url)
            received = urlsplit(origin)
            if (received.scheme, received.netloc) != (allowed.scheme, allowed.netloc):
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403, headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "version": settings.app_version}
