"""Replace this provider with the algorithm teammate's integration."""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class RecommendationContext:
    session_id: str
    catalog_movie_ids: Sequence[int]
    shown_movie_ids: frozenset[int]


class RecommendationProvider(Protocol):
    async def movie_ids(self, context: RecommendationContext, limit: int) -> list[int]: ...


class MockRecommendationProvider:
    """Catalog order only: no ranking, scoring, embeddings, or recommendation algorithm."""

    async def movie_ids(self, context: RecommendationContext, limit: int) -> list[int]:
        return list(dict.fromkeys(
            movie_id for movie_id in context.catalog_movie_ids
            if movie_id not in context.shown_movie_ids
        ))[:limit]
