from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.models import RunbookChunk
from app.rca.indexer import DEFAULT_RUNBOOKS, runbook_indexer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed operational runbooks if runbook corpus is empty
    async with AsyncSessionLocal() as session:
        stmt = select(RunbookChunk).limit(1)
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            for rb in DEFAULT_RUNBOOKS:
                await runbook_indexer.index_runbook(
                    session=session,
                    runbook_id=rb["runbook_id"],
                    title=rb["title"],
                    service=rb["service"],
                    markdown_content=rb["content"],
                )

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "healthy", "service": "traceguard-backend"}

