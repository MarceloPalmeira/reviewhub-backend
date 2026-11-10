from typing import ClassVar

from pydantic import Field

from reviewhub_core.plugins import ContentSchema, DomainPlugin


class Metadata(ContentSchema):
    seasons: int | None = Field(default=None, ge=0)
    episodes: int | None = Field(default=None, ge=0)
    status: str | None = None


class Plugin(DomainPlugin):
    identifier = "series"
    external_provider = "tmdb"
    manual_required_fields = ("seasons", "status")
    schema = Metadata
    feature_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "episode_metadata": ("episodes",)
    }
    capabilities = frozenset({"episode_metadata"})
