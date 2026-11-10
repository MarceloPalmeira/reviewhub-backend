"""Teste explícito e opcional de conectividade; nunca roda por padrão."""

import os

import pytest

from services.catalog.providers.registry import configured_provider


@pytest.mark.parametrize(
    ("provider_name", "domain", "query"),
    [
        ("tmdb", "movies", "Matrix"),
        ("tmdb", "series", "Friends"),
        ("igdb", "video_games", "Zelda"),
        ("musicbrainz", "music_albums", "Abbey Road"),
        ("football", "football_matches", "Brasil"),
    ],
)
def test_live_search(provider_name, domain, query):
    if os.getenv("RUN_EXTERNAL_INTEGRATION") != "1":
        pytest.skip("Teste externo exige RUN_EXTERNAL_INTEGRATION=1")
    provider = configured_provider(provider_name)
    if provider is None:
        pytest.skip("Provedor não configurado")
    assert isinstance(provider.search(query, domain), list)
