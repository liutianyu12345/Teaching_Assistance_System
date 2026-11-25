import asyncio
import os
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy import text
from . import access, classroom, lessons, practice, resources, tasks
from .db import migrate, transaction, log
from .seed import seed


@asynccontextmanager
async def lifespan(app):
    migrate()
    seed()

    async def recovery_loop():
        while True:
            await asyncio.to_thread(tasks.recover)
            await asyncio.sleep(60)

    task = None
    if os.getenv("TASK_MODE") != "celery":
        task = asyncio.create_task(recovery_loop())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="知衡 · 初中物理教学辅助系统",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
for module in (access, resources, lessons, classroom, practice, tasks):
    app.include_router(module.router)


@app.exception_handler(ValidationError)
async def validation(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)[:1000]})


@app.middleware("http")
async def audit_denied(request: Request, call_next):
    response = await call_next(request)
    if response.status_code in (403, 409):
        user = await asyncio.to_thread(access.identity, request.cookies.get("session"))
        if user:

            def record():
                with transaction() as db:
                    log(db, user["id"], "操作被拒绝", request.url.path, str(response.status_code))

            await asyncio.to_thread(record)
    return response


@app.get("/api/health")
def health():
    with transaction(False) as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


# A built checkout can be demonstrated with a single local Python process.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="web")
