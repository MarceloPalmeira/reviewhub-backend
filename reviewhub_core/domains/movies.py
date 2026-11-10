from pydantic import Field

from reviewhub_core.plugins import ContentSchema, DomainPlugin


class Metadata(ContentSchema):
    director: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    cast: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1888, le=2100)


class Plugin(DomainPlugin):
    identifier = "movies"
    external_provider = "tmdb"
    manual_required_fields = ("director", "duration_minutes", "year")
    schema = Metadata
    capabilities = frozenset()
