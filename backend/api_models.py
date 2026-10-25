"""Public wire schemas, shared by response validation and exported OpenAPI."""

from datetime import datetime
from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SessionJoined(BaseModel):
    session_id: UUID


class SessionCreated(SessionJoined):
    invite_token: str


class InvitationResponse(BaseModel):
    invite_token: str


class RoundResponse(BaseModel):
    round_id: Optional[UUID]


class QueueResponse(BaseModel):
    added: int


class GroupSession(BaseModel):
    id: UUID
    host_user_id: UUID
    status: Literal["lobby", "active", "ended"]
    created_at: datetime
    expires_at: datetime
    ended_at: Optional[datetime]


class SessionMember(BaseModel):
    session_id: UUID
    user_id: UUID
    is_voter: bool
    joined_at: datetime
    last_seen_at: datetime
    left_at: Optional[datetime]


class SessionMovie(BaseModel):
    session_id: UUID
    movie_id: int
    position: int
    shown_at: Optional[datetime]


class VotingRound(BaseModel):
    id: UUID
    session_id: UUID
    movie_id: int
    opened_at: datetime
    closed_at: Optional[datetime]
    close_reason: Optional[Literal["completed", "skipped", "ended"]]


class RoundParticipant(BaseModel):
    session_id: UUID
    round_id: UUID
    user_id: UUID
    excluded_at: Optional[datetime]


class VoteRecord(BaseModel):
    session_id: UUID
    round_id: UUID
    user_id: UUID
    value: Literal[-1, 1]
    created_at: datetime
    updated_at: datetime


class SessionState(BaseModel):
    session: GroupSession
    session_members: list[SessionMember]
    session_movies: list[SessionMovie]
    voting_rounds: list[VotingRound]
    round_participants: list[RoundParticipant]
    votes: list[VoteRecord]


class ValidationIssue(BaseModel):
    loc: list[Union[str, int]]
    msg: str
    type: str


class ErrorResponse(BaseModel):
    detail: Union[str, list[ValidationIssue]]
