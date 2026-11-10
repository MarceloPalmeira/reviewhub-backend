from abc import ABC, abstractmethod
from importlib import import_module
from importlib.metadata import entry_points
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ContentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RatingStrategy(ABC):
    @abstractmethod
    def validate(self, rating: float) -> float: ...


class HalfStarRating(RatingStrategy):
    def validate(self, rating: float) -> float:
        if not 0 <= rating <= 5 or rating * 2 != int(rating * 2):
            raise ValueError("A nota deve estar entre 0 e 5 em incrementos de 0,5")
        return rating


class ReviewPolicy:
    def __init__(self, rating: RatingStrategy | None = None):
        self.rating = rating or HalfStarRating()

    def validate(self, rating: float, text: str) -> None:
        self.rating.validate(rating)
        if not text.strip():
            raise ValueError("O texto da review não pode estar vazio")


class DomainPlugin(ABC):
    identifier: ClassVar[str]
    schema: ClassVar[type[ContentSchema]]
    capabilities: ClassVar[frozenset[str]] = frozenset()
    external_provider: ClassVar[str | None] = None
    manual_required_fields: ClassVar[tuple[str, ...]] = ()
    feature_fields: ClassVar[dict[str, tuple[str, ...]]] = {}

    def validate_metadata(
        self, metadata: dict, features: list[str] | None = None
    ) -> dict:
        missing = [
            field
            for field in self.manual_required_fields
            if metadata.get(field) is None
        ]
        if missing:
            raise ValueError(f"Campos obrigatórios ausentes: {', '.join(missing)}")
        if features is not None:
            for feature, fields in self.feature_fields.items():
                if feature in features and any(
                    metadata.get(field) is None for field in fields
                ):
                    raise ValueError(f"{feature} exige os campos: {', '.join(fields)}")
                if feature not in features and any(
                    field in metadata for field in fields
                ):
                    raise ValueError(f"{feature} não está habilitada")
        return self.schema.model_validate(metadata).model_dump(
            exclude_none=True, mode="json"
        )

    def visible_metadata(self, metadata: dict, features: list[str]) -> dict:
        hidden = {
            field
            for feature, fields in self.feature_fields.items()
            if feature not in features
            for field in fields
        }
        return {key: value for key, value in metadata.items() if key not in hidden}

    def review_policy(self, specific: bool = False) -> ReviewPolicy:
        return ReviewPolicy()


class ContentProvider(ABC):
    @abstractmethod
    def get(self, content_id: str) -> dict: ...


# Os módulos só são importados quando o produto seleciona o domínio.
PLUGIN_MODULES = {
    "movies": "reviewhub_core.domains.movies",
    "series": "reviewhub_core.domains.series",
    "video_games": "reviewhub_core.domains.video_games",
    "football_matches": "reviewhub_core.domains.football_matches",
    "music_albums": "reviewhub_core.domains.music_albums",
}


def available_plugins():
    external = {entry.name: entry for entry in entry_points(group="reviewhub.domains")}
    if set(external) & PLUGIN_MODULES.keys():
        raise ValueError("Um plugin externo conflita com um domínio interno")
    return {**PLUGIN_MODULES, **external}


class FeatureRegistry:
    def __init__(self, domains: list[str]):
        self.plugins: dict[str, DomainPlugin] = {}
        available = available_plugins()
        for domain in domains:
            if domain not in available:
                raise ValueError(f"Domínio desconhecido: {domain}")
            source = available[domain]
            plugin = (
                import_module(source).Plugin()
                if isinstance(source, str)
                else source.load()()
            )
            if not isinstance(plugin, DomainPlugin) or plugin.identifier != domain:
                raise ValueError(f"Plugin inválido: {domain}")
            self.plugins[domain] = plugin

    def get(self, domain: str) -> DomainPlugin:
        if domain not in self.plugins:
            raise ValueError(f"Domínio não habilitado: {domain}")
        return self.plugins[domain]
