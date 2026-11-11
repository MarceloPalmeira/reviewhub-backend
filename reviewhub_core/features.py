from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reviewhub_core.plugins import FeatureRegistry, available_plugins


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    domains: list[str] = Field(min_length=1)
    features: list[str]

    @model_validator(mode="after")
    def validate_product(self):
        FeatureValidator().validate(self.domains, self.features)
        return self


class FeatureValidator:
    mandatory: ClassVar[set[str]] = {"identity", "catalog", "reviews", "rating"}
    optional: ClassVar[set[str]] = {
        "external_tmdb",
        "external_igdb",
        "external_musicbrainz",
        "external_football",
        "imdb_ratings",
        "comments",
        "custom_lists",
        "recommendations",
        "review_likes",
        "user_follows",
        "social_feed",
        "spoiler_control",
        "episode_metadata",
        "track_listing",
        "football_scoreboard",
        "game_platforms",
        "domain_specific_rating",
    }
    dependencies: ClassVar[dict[str, str]] = {
        "social_feed": "user_follows",
        "comments": "reviews",
        "recommendations": "reviews",
        "custom_lists": "catalog",
        "review_likes": "reviews",
        "episode_metadata": "series",
        "track_listing": "music_albums",
        "football_scoreboard": "football_matches",
        "game_platforms": "video_games",
    }

    def validate(self, domains: list[str], features: list[str]) -> None:
        domain_set, enabled = set(domains), set(features)
        if not domain_set:
            raise ValueError("Selecione pelo menos um domínio")
        if len(domains) != len(domain_set) or len(features) != len(enabled):
            raise ValueError("Domínios e features não podem estar duplicados")
        unknown = domain_set - available_plugins().keys()
        if unknown:
            raise ValueError(f"Domínios desconhecidos: {sorted(unknown)}")
        unknown_features = enabled - self.mandatory - self.optional
        if unknown_features:
            raise ValueError(
                f"Features desconhecidas ou não implementadas: {sorted(unknown_features)}"
            )
        missing = self.mandatory - enabled
        if missing:
            raise ValueError(f"Features obrigatórias ausentes: {sorted(missing)}")
        for feature, dependency in self.dependencies.items():
            if feature in enabled and dependency not in enabled | domain_set:
                raise ValueError(f"{feature} exige {dependency}")
        provider_domains = {
            "external_tmdb": {"movies", "series"},
            "external_igdb": {"video_games"},
            "external_musicbrainz": {"music_albums"},
            "external_football": {"football_matches"},
            "imdb_ratings": {"movies", "series"},
        }
        for feature, compatible in provider_domains.items():
            if feature in enabled and not domain_set.intersection(compatible):
                raise ValueError(f"{feature} exige um domínio compatível")
        registry = FeatureRegistry(domains)
        if "domain_specific_rating" in enabled and not any(
            "domain_specific_rating" in p.capabilities
            for p in registry.plugins.values()
        ):
            raise ValueError("domain_specific_rating exige um plugin compatível")
