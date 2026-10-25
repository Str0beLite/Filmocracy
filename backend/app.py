import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Literal, Optional
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from api_models import (
    ErrorResponse,
    HealthResponse,
    InvitationResponse,
    QueueResponse,
    RoundResponse,
    SessionCreated,
    SessionJoined,
    SessionState,
)
from recommendations import (
    MockRecommendationProvider,
    RecommendationContext,
    RecommendationProvider,
)

logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)
provider: RecommendationProvider = MockRecommendationProvider()


class Supabase:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
        self.secret = os.environ["SUPABASE_SECRET_KEY"]
        self.client = httpx.AsyncClient(timeout=15)

    async def request(self, method, path, *, token=None, privileged=False, body=None, params=None):
        key = self.secret if privileged else self.key
        headers = {"apikey": key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Legacy service-role JWTs need Authorization as well as apikey.
        elif privileged and key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        try:
            response = await self.client.request(
                method, self.url + path, headers=headers, json=body, params=params
            )
        except httpx.RequestError as exc:
            logger.warning("Supabase request failed: %s %s (%s)", method, path, type(exc).__name__)
            raise HTTPException(503, "Supabase unavailable") from exc
        if response.is_error:
            try:
                error = response.json()
            except ValueError:
                error = {}
            code = error.get("error_code") or error.get("code")
            status = {"42501": 403, "22023": 400, "23503": 400, "23514": 400}.get(code)
            if response.status_code in (401, 403):
                status = response.status_code
            if path == "/auth/v1/user" and code == "bad_jwt":
                status = 401
            if not status:
                status = 502
            # Never log auth headers, tokens, or upstream response bodies.
            raise HTTPException(status, "Request rejected by Supabase")
        return response.json() if response.content else None

    async def rpc(self, name, body, *, token=None, privileged=False):
        return await self.request(
            "POST", f"/rest/v1/rpc/{name}", token=token, privileged=privileged, body=body
        )


async def sweep(db):
    while True:
        try:
            await db.rpc("sweep_sessions", {}, privileged=True)
        except HTTPException:
            logger.error("Session expiry sweep failed; retrying in 10 seconds")
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app):
    app.state.db = Supabase()
    task = None
    if os.getenv("SWEEP_ENABLED", "true").lower() == "true":
        task = asyncio.create_task(sweep(app.state.db))
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await app.state.db.client.aclose()


app = FastAPI(
    title="Tandem backend",
    version="0.1.0",
    lifespan=lifespan,
    responses={status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 422, 502, 503)},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


async def user_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)
):
    if credentials is None:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    # Auth server verifies the token; never trust a decoded JWT or a body user_id.
    request.state.user = await request.app.state.db.request(
        "GET", "/auth/v1/user", token=credentials.credentials
    )
    return credentials.credentials


class CreateSession(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)


class JoinSession(CreateSession):
    invite_token: str = Field(min_length=64, max_length=64)


class Vote(BaseModel):
    round_id: UUID
    value: Literal[-1, 1]


class Control(BaseModel):
    action: Literal["start", "skip", "end"]
    expected_round_id: Optional[UUID] = None


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.post("/sessions", response_model=SessionCreated)
async def create_session(body: CreateSession, request: Request, token=Depends(user_token)):
    return await request.app.state.db.rpc(
        "create_session", {"p_name": body.display_name}, token=token
    )


@app.post("/sessions/join", response_model=SessionJoined)
async def join_session(body: JoinSession, request: Request, token=Depends(user_token)):
    session_id = await request.app.state.db.rpc(
        "join_session", {"p_token": body.invite_token, "p_name": body.display_name}, token=token
    )
    return {"session_id": session_id}


@app.post("/sessions/{session_id}/invitation", response_model=InvitationResponse)
async def invitation(session_id: UUID, request: Request, token=Depends(user_token)):
    value = await request.app.state.db.rpc(
        "rotate_invite", {"p_session": str(session_id)}, token=token
    )
    return {"invite_token": value}


@app.get("/sessions/{session_id}", response_model=SessionState)
async def session_state(session_id: UUID, request: Request, token=Depends(user_token)):
    params = {"session_id": f"eq.{session_id}", "select": "*"}
    sessions = await request.app.state.db.request(
        "GET",
        "/rest/v1/group_sessions",
        token=token,
        params={"id": f"eq.{session_id}", "select": "*"},
    )
    if not sessions:
        raise HTTPException(404, "Session not found")
    tables = ("session_members", "session_movies", "voting_rounds", "round_participants", "votes")
    rows = await asyncio.gather(
        *(
            request.app.state.db.request("GET", f"/rest/v1/{table}", token=token, params=params)
            for table in tables
        )
    )
    return {"session": sessions[0], **dict(zip(tables, rows))}


@app.post("/sessions/{session_id}/heartbeat", response_model=RoundResponse)
async def heartbeat(session_id: UUID, request: Request, token=Depends(user_token)):
    return {
        "round_id": await request.app.state.db.rpc(
            "heartbeat", {"p_session": str(session_id), "p_leave": False}, token=token
        )
    }


@app.post("/sessions/{session_id}/leave", response_model=RoundResponse)
async def leave(session_id: UUID, request: Request, token=Depends(user_token)):
    return {
        "round_id": await request.app.state.db.rpc(
            "heartbeat", {"p_session": str(session_id), "p_leave": True}, token=token
        )
    }


@app.post("/sessions/{session_id}/votes", response_model=RoundResponse)
async def vote(session_id: UUID, body: Vote, request: Request, token=Depends(user_token)):
    return {
        "round_id": await request.app.state.db.rpc(
            "cast_vote",
            {"p_session": str(session_id), "p_round": str(body.round_id), "p_value": body.value},
            token=token,
        )
    }


@app.post("/sessions/{session_id}/control", response_model=RoundResponse)
async def control(session_id: UUID, body: Control, request: Request, token=Depends(user_token)):
    if body.action == "skip" and body.expected_round_id is None:
        raise HTTPException(422, "Skipping requires expected_round_id")
    return {
        "round_id": await request.app.state.db.rpc(
            "control_session",
            {
                "p_session": str(session_id),
                "p_action": body.action,
                "p_expected_round": str(body.expected_round_id) if body.expected_round_id else None,
            },
            token=token,
        )
    }


@app.post("/sessions/{session_id}/queue", response_model=QueueResponse)
async def prepare_queue(session_id: UUID, request: Request, token=Depends(user_token)):
    if hasattr(request.app.state, "integration"):
        return await request.app.state.integration.queue(str(session_id), token)
    # Read as caller; installation RPC also enforces host authority under a lock.
    sessions = await request.app.state.db.request(
        "GET",
        "/rest/v1/group_sessions",
        token=token,
        params={"id": f"eq.{session_id}", "select": "id"},
    )
    if not sessions:
        raise HTTPException(404, "Session not found")
    catalog = await request.app.state.db.request(
        "GET", "/rest/v1/movies", token=token, params={"select": "id", "order": "id", "limit": 100}
    )
    queued = await request.app.state.db.request(
        "GET",
        "/rest/v1/session_movies",
        token=token,
        params={"session_id": f"eq.{session_id}", "select": "movie_id"},
    )
    context = RecommendationContext(
        str(session_id), [m["id"] for m in catalog], frozenset(m["movie_id"] for m in queued)
    )
    movie_ids = await provider.movie_ids(context, 100)
    count = await request.app.state.db.rpc(
        "enqueue_movies", {"p_session": str(session_id), "p_movies": movie_ids}, token=token
    )
    return {"added": count}
