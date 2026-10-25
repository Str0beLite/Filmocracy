"""One SQLite-backed API: all main recommendation routes plus durable session voting."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from session_recommendations import SessionRecommendations
from sqlite_session_store import SessionStore
from sqlite_sessions import router
from tandem import config, vision
from tandem.api import create_app as recommendation_app
from tandem.auth import current_user

log = logging.getLogger(__name__)


def create_app(catalog=None, store=None, metadata=None, clock=None):
    def principal(user=Depends(current_user)):
        return user

    training = os.getenv("TANDEM_TRAINING_ENABLED", "0") == "1"
    rec = recommendation_app(catalog=catalog, store=store, start_trainer=training, principal=principal)

    async def maintain(app):
        while True:
            if os.getenv("SWEEP_ENABLED", "true").lower() == "true":
                try:
                    await asyncio.to_thread(app.state.sessions.sweep)
                except Exception:
                    log.warning("Session expiry sweep deferred; will retry")
            try:
                version, _ = app.state.tandem["trainer"].current()
                synced = await asyncio.to_thread(app.state.sessions.sync_feedback, version)
                if training:
                    for _ in range(synced):
                        app.state.tandem["trainer"].notify_event()
            except Exception:
                log.warning("Vote feedback sync deferred; accepted votes remain saved")
            await asyncio.sleep(10)

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("RAILWAY_ENVIRONMENT_ID"):
            if os.getenv("RAILWAY_VOLUME_MOUNT_PATH") != "/data" or str(config.DATA_DIR) != "/data":
                raise RuntimeError(
                    "Railway requires a persistent volume and TANDEM_DATA_DIR at /data"
                )
            if config.DEV_AUTH:
                raise RuntimeError("TANDEM_DEV_AUTH must be disabled on Railway")
            if config.FAKE_ENCODER:
                raise RuntimeError("TANDEM_FAKE_ENCODER must be disabled on Railway")
        task = None
        try:
            async with rec.router.lifespan_context(rec):
                app.state.tandem = rec.state.tandem
                rows = (
                    metadata
                    if metadata is not None
                    else json.loads(
                        (config.CATALOG_DIR / "session_movie_metadata.json").read_text()
                    )
                )
                kwargs = {"clock": clock} if clock is not None else {}
                app.state.sessions = SessionStore(
                    rec.state.tandem["store"], rec.state.tandem["catalog"], rows, **kwargs
                )
                async with httpx.AsyncClient(timeout=15) as client:
                    app.state.integration = SessionRecommendations(
                        app.state.sessions, rec.state.tandem, client
                    )
                    task = asyncio.create_task(maintain(app))
                    try:
                        yield
                    finally:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
        finally:
            if not store and rec.state.tandem.get("store"):
                rec.state.tandem["store"].db.close()

    app = FastAPI(title="Filmocracy unified SQLite backend", version="0.3.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            v.strip()
            for v in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
            if v.strip()
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    app.include_router(router)
    rec_routes = APIRouter()
    for route in rec.router.routes:
        if getattr(route, "path", "") not in (
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        ):
            rec_routes.routes.append(route)

    app.include_router(rec_routes)

    @app.get("/health")
    def health(request: Request):
        state = request.app.state.tandem
        version, _ = state["trainer"].current()
        return {
            "status": "ok",
            "ok": True,
            "w_version": version,
            "movies": len(state["catalog"].movies),
            "events": state["store"].count_events(),
            "vision": vision.has_api_key(),
        }

    @app.get("/ready")
    def ready(request: Request):
        state = request.app.state.tandem
        state["store"]._all("SELECT 1")
        return {
            "status": "ready",
            "database": "sqlite",
            "sqlite_movies": request.app.state.sessions.movies(0, 1)["total"],
            "training_enabled": training,
            "w_version": state["trainer"].current()[0],
            "movies": len(state["catalog"].movies),
        }

    return app


app = create_app()
