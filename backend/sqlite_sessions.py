"""Google-authenticated session API and WebSocket/SSE snapshots over SQLite."""

import asyncio
import json
import os
from typing import Literal, Optional
from uuid import UUID

from api_models import (
    GroupSession,
    InvitationResponse,
    QueueResponse,
    RoundParticipant,
    RoundResponse,
    SessionCreated,
    SessionJoined,
    SessionMember,
    SessionMovie,
    VoteRecord,
    VotingRound,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect
from tandem.auth import current_user

router = APIRouter()


@router.websocket("/sessions/{sid}/ws")
async def session_socket(sid: UUID, websocket: WebSocket):
    # Browser sockets cannot send Authorization headers; keep credentials out of URLs.
    origins = {
        value.strip()
        for value in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    }
    origin = websocket.headers.get("origin")
    if origin and origin not in origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = message.get("token") if isinstance(message, dict) else None
        if (
            not isinstance(message, dict)
            or message.get("type") != "auth"
            or not isinstance(token, str)
            or not token
            or len(token) > 8192
        ):
            await websocket.close(code=4401)
            return
        try:
            user = await asyncio.to_thread(current_user, authorization=f"Bearer {token}")
        except HTTPException:
            await websocket.close(code=4401)
            return
        sessions = websocket.app.state.sessions
        revision = None
        while True:
            try:
                state = await asyncio.to_thread(sessions.snapshot, str(sid), user)
            except HTTPException:
                await websocket.close(code=4403)
                return
            if state["session"]["revision"] != revision:
                revision = state["session"]["revision"]
                await websocket.send_json({"type": "state", "revision": revision, "state": state})
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=1)
            except asyncio.TimeoutError:
                continue
            if isinstance(message, dict) and message.get("type") == "heartbeat":
                await asyncio.to_thread(sessions.heartbeat, str(sid), user)
            elif isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.close(code=1008)
                return
    except asyncio.TimeoutError:
        await websocket.close(code=4401)
    except (ValueError, TypeError):
        await websocket.close(code=1008)
    except HTTPException:
        await websocket.close(code=4403)
    except WebSocketDisconnect:
        return


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


class Feed(BaseModel):
    feed_id: str = Field(min_length=1, max_length=128)


class SQLiteGroupSession(GroupSession):
    host_user_id: str
    revision: int


class SQLiteMember(SessionMember):
    user_id: str


class SQLiteParticipant(RoundParticipant):
    user_id: str


class SQLiteVote(VoteRecord):
    user_id: str


class Profile(BaseModel):
    id: str
    display_name: Optional[str]


class SQLiteSessionState(BaseModel):
    profiles: list[Profile]
    session: SQLiteGroupSession
    session_members: list[SQLiteMember]
    session_movies: list[SessionMovie]
    voting_rounds: list[VotingRound]
    round_participants: list[SQLiteParticipant]
    votes: list[SQLiteVote]


class RankedMovie(BaseModel):
    movie_id: int
    unanimous: bool
    likes: int
    dislikes: int
    predicted_score: float


@router.get("/profiles/me", response_model=Profile)
def profile(request: Request, user=Depends(current_user)):
    return request.app.state.sessions.get_profile(user)


@router.post("/profiles/me", response_model=Profile)
def update_profile(body: CreateSession, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.update_profile(user, body.display_name)


@router.post("/sessions", response_model=SessionCreated)
def create(body: CreateSession, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.create(user, body.display_name)


@router.post("/sessions/join", response_model=SessionJoined)
def join(body: JoinSession, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.join(user, body.display_name, body.invite_token)


@router.get("/sessions/{sid}", response_model=SQLiteSessionState)
def snapshot(sid: UUID, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.snapshot(str(sid), user)


@router.post("/sessions/{sid}/invitation", response_model=InvitationResponse)
def invitation(sid: UUID, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.invitation(str(sid), user)


@router.post("/sessions/{sid}/heartbeat", response_model=RoundResponse)
def heartbeat(sid: UUID, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.heartbeat(str(sid), user)


@router.post("/sessions/{sid}/leave", response_model=RoundResponse)
def leave(sid: UUID, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.heartbeat(str(sid), user, True)


@router.post("/sessions/{sid}/votes", response_model=RoundResponse)
def vote(sid: UUID, body: Vote, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.vote(str(sid), user, str(body.round_id), body.value)


@router.post("/sessions/{sid}/control", response_model=RoundResponse)
def control(sid: UUID, body: Control, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.control(
        str(sid), user, body.action, str(body.expected_round_id) if body.expected_round_id else None
    )


@router.post("/sessions/{sid}/feed", response_model=Feed)
def bind(sid: UUID, body: Feed, request: Request, user=Depends(current_user)):
    return request.app.state.sessions.bind(str(sid), user, body.feed_id)


@router.post("/sessions/{sid}/queue", response_model=QueueResponse)
async def queue(sid: UUID, request: Request, user=Depends(current_user)):
    return await request.app.state.integration.queue(str(sid), user)


@router.get("/sessions/{sid}/rankings", response_model=list[RankedMovie])
async def rankings(sid: UUID, request: Request, user=Depends(current_user)):
    return await request.app.state.integration.rankings(str(sid), user)


@router.get("/movies")
def movies(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(current_user),
):
    return request.app.state.sessions.movies(offset, limit)


@router.get("/session-catalog")
def catalog(request: Request, user=Depends(current_user)):
    cat = request.app.state.tandem["catalog"]
    return [
        {**cat.public(cat.id_to_idx[row["id"]]), **row}
        for row in request.app.state.sessions.metadata()
    ]


async def session_events(sessions, sid, user, request, interval=1):
    revision = None
    while not await request.is_disconnected():
        try:
            state = await asyncio.to_thread(sessions.snapshot, sid, user)
        except HTTPException:
            yield "event: access_revoked\ndata: {}\n\n"
            return
        if state["session"]["revision"] != revision:
            revision = state["session"]["revision"]
            yield f"id: {revision}\nevent: state\ndata: {json.dumps(state)}\n\n"
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(interval)


@router.get("/sessions/{sid}/events")
async def events(sid: UUID, request: Request, user=Depends(current_user)):
    sessions = request.app.state.sessions
    await asyncio.to_thread(sessions.snapshot, str(sid), user)
    return StreamingResponse(
        session_events(sessions, str(sid), user, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
