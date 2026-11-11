import os
from functools import lru_cache

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.providers.base import ProviderError
from services.catalog.providers.football import FootballProvider
from services.catalog.providers.igdb import IGDBProvider
from services.catalog.providers.musicbrainz import MusicBrainzProvider
from services.catalog.providers.omdb import OMDbProvider
from services.catalog.providers.tmdb import TMDBProvider


@lru_cache(maxsize=4)
def configured_provider(name):
    if name == "tmdb" and os.getenv("TMDB_API_TOKEN"):
        return TMDBProvider(os.environ["TMDB_API_TOKEN"])
    if (
        name == "igdb"
        and os.getenv("IGDB_CLIENT_ID")
        and os.getenv("IGDB_CLIENT_SECRET")
    ):
        return IGDBProvider(
            os.environ["IGDB_CLIENT_ID"], os.environ["IGDB_CLIENT_SECRET"]
        )
    if name == "musicbrainz" and os.getenv("MUSICBRAINZ_USER_AGENT"):
        agent = os.environ["MUSICBRAINZ_USER_AGENT"]
        if "@" in agent or "http" in agent:
            return MusicBrainzProvider(agent)
    if name == "football" and os.getenv("FOOTBALL_DATA_API_TOKEN"):
        return FootballProvider(os.environ["FOOTBALL_DATA_API_TOKEN"])
    if name == "omdb" and os.getenv("OMDB_API_KEY"):
        return OMDbProvider(os.environ["OMDB_API_KEY"])
    return None


def provider_name(domain, product):
    if domain not in product.domains:
        raise ProviderError("Provedor ou domínio indisponível neste produto", 404)
    name = FeatureRegistry(product.domains).get(domain).external_provider
    if not name or f"external_{name}" not in product.features:
        raise ProviderError("Provedor ou domínio indisponível neste produto", 404)
    return name
