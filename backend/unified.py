"""Production entrypoint: one lifespan, one OpenAPI, no training worker."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import app as sessions
from session_recommendations import SessionRecommendations
from tandem.api import create_app as recommendation_app

log = logging.getLogger(__name__)


class AttachFeed(BaseModel):
    feed_id: str


class RankedMovie(BaseModel):
    movie_id: int
    unanimous: bool
    likes: int
    dislikes: int
    predicted_score: float


class Ready(BaseModel):
    status: Literal["ready"]
    training_enabled: bool
    w_version: int
    movies: int


def create_app(catalog=None, store=None, db=None):
    async def principal(request: Request, token=Depends(sessions.user_token)):
        return request.state.user["id"]

    rec = recommendation_app(catalog=catalog, store=store, start_trainer=False, principal=principal)

    async def reconcile(integration):
        while True:
            try:
                await integration.reconcile()
            except Exception:
                log.warning("Vote feedback sync deferred; will retry")
            await asyncio.sleep(10)

    @asynccontextmanager
    async def lifespan(app):
        if (
            os.getenv("RAILWAY_ENVIRONMENT_ID")
            and os.getenv("RAILWAY_VOLUME_MOUNT_PATH") != "/data"
        ):
            raise RuntimeError("Railway requires a persistent volume mounted at /data")
        from tandem import config

        if os.getenv("RAILWAY_ENVIRONMENT_ID") and str(config.DATA_DIR) != "/data":
            raise RuntimeError("Railway TANDEM_DATA_DIR must be /data")
        app.state.db = db or sessions.Supabase()
        tasks = []
        try:
            async with rec.router.lifespan_context(rec):
                app.state.tandem = rec.state.tandem
                integration = SessionRecommendations(app.state.db, rec.state.tandem)
                app.state.integration = integration
                tasks.append(asyncio.create_task(reconcile(integration)))
                if os.getenv("SWEEP_ENABLED", "true").lower() == "true":
                    tasks.append(asyncio.create_task(sessions.sweep(app.state.db)))
                yield
        finally:
            for task in tasks:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if not db:
                await app.state.db.client.aclose()
            if not store and rec.state.tandem.get("store"):
                rec.state.tandem["store"].db.close()

    app = FastAPI(title="Tandem unified backend", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            v.strip()
            for v in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
            if v.strip()
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.router.routes.extend(
        route
        for route in sessions.app.router.routes
        if getattr(route, "path", "")
        not in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")
    )
    # Keep a single /health route and a single documentation surface.
    for route in rec.router.routes:
        if getattr(route, "path", "") not in (
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        ):
            app.router.routes.append(route)

    @app.post("/sessions/{session_id}/feed", response_model=AttachFeed)
    async def attach(
        session_id: UUID, body: AttachFeed, request: Request, token=Depends(sessions.user_token)
    ):
        return await request.app.state.integration.bind(
            str(session_id), body.feed_id, request.state.user["id"], token
        )

    @app.get("/sessions/{session_id}/rankings", response_model=list[RankedMovie])
    async def rankings(session_id: UUID, request: Request, token=Depends(sessions.user_token)):
        return await request.app.state.integration.rankings(str(session_id), token)

    @app.get("/ready", response_model=Ready)
    async def ready(request: Request):
        version, _ = request.app.state.tandem["trainer"].current()
        return {
            "status": "ready",
            "training_enabled": False,
            "w_version": version,
            "movies": len(request.app.state.tandem["catalog"].movies),
        }

    return app


app = create_app()
