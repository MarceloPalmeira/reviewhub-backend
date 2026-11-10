from typing import ClassVar

from pydantic import Field

from reviewhub_core.plugins import ContentSchema, DomainPlugin


class Metadata(ContentSchema):
    platforms: list[str] | None = None
    developer: str | None = None
    genre: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)


class Plugin(DomainPlugin):
    identifier = "video_games"
    external_provider = "igdb"
    manual_required_fields = ("developer", "genre", "year")
    schema = Metadata
    feature_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "game_platforms": ("platforms",)
    }
    capabilities = frozenset({"game_platforms"})
