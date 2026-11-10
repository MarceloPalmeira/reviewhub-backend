from datetime import date
from typing import ClassVar

from pydantic import Field

from reviewhub_core.plugins import (
    ContentSchema,
    DomainPlugin,
    HalfStarRating,
    ReviewPolicy,
)


class Metadata(ContentSchema):
    home_team: str
    away_team: str
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    competition: str
    match_date: date
    status: str | None = None
    season: str | None = None


class Plugin(DomainPlugin):
    identifier = "football_matches"
    external_provider = "football"
    manual_required_fields = ()
    schema = Metadata
    feature_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "football_scoreboard": ("home_score", "away_score")
    }
    capabilities = frozenset({"football_scoreboard", "domain_specific_rating"})

    def review_policy(self, specific: bool = False) -> ReviewPolicy:
        return ReviewPolicy(MatchRating()) if specific else ReviewPolicy()


class MatchRating(HalfStarRating):
    def validate(self, rating: float) -> float:
        super().validate(rating)
        if rating == 0:
            raise ValueError(
                "A avaliação específica de partidas deve ser maior que zero"
            )
        return rating
