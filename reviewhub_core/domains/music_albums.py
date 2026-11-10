from typing import ClassVar

from pydantic import Field

from reviewhub_core.plugins import ContentSchema, DomainPlugin


class Metadata(ContentSchema):
    artist: str | None = None
    genre: str | None = None
    year: int | None = Field(default=None, ge=1877, le=2100)
    tracks: list[str] | None = None


class Plugin(DomainPlugin):
    identifier = "music_albums"
    external_provider = "musicbrainz"
    manual_required_fields = ("artist", "genre", "year")
    schema = Metadata
    feature_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "track_listing": ("tracks",)
    }
    capabilities = frozenset({"track_listing"})
