from datetime import UTC, datetime

import httpx
import pytest

from reviewhub_core.features import Product
from services.catalog.providers.base import ProviderError, TTLCache, request
from services.catalog.providers.football import FootballProvider
from services.catalog.providers.igdb import IGDBProvider
from services.catalog.providers.musicbrainz import MusicBrainzProvider
from services.catalog.providers.registry import provider_name
from services.catalog.providers.tmdb import TMDBProvider


def test_tmdb_search_details_cache_and_portuguese():
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["authorization"] == "Bearer token-test-only"
        assert req.url.params["language"] == "pt-BR"
        if req.url.path.endswith("/search/movie"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 42,
                            "title": "Filme",
                            "overview": "Sinopse",
                            "poster_path": "/poster.jpg",
                            "release_date": "2020-03-12",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 42,
                "title": "Filme",
                "runtime": 100,
                "release_date": "2020-03-12",
                "genres": [{"name": "Drama"}],
                "backdrop_path": "/fundo.jpg",
                "credits": {
                    "crew": [{"job": "Director", "name": "Ana"}],
                    "cast": [{"name": "Bia"}],
                },
            },
        )

    provider = TMDBProvider(
        "token-test-only", httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.gate.interval = 0
    assert provider.search("filme", "movies")[0].cover_url.endswith("/poster.jpg")
    assert provider.search("filme", "movies")[0].external_id == "42"
    detail = provider.get_details("42", "movies")
    assert detail.metadata == {
        "director": "Ana",
        "duration_minutes": 100,
        "cast": ["Bia"],
        "year": 2020,
    }
    assert detail.genres == ["Drama"] and detail.backdrop_url.endswith("/fundo.jpg")
    assert provider.get_details("42", "movies") == detail
    assert len(calls) == 2
    assert "token-test-only" not in detail.model_dump_json()


@pytest.mark.parametrize(
    "status,expected", [(401, 503), (403, 503), (404, 404), (429, 429), (500, 503)]
)
def test_provider_error_mapping(status, expected):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status))
    )
    with pytest.raises(ProviderError) as error:
        request(client, "GET", "https://example.invalid/")
    assert error.value.status == expected
    assert "example.invalid" not in str(error.value)


def test_provider_timeout_and_cache_only_successes():
    def handler(req):
        raise httpx.ReadTimeout("secret details", request=req)

    with pytest.raises(ProviderError) as error:
        request(
            httpx.Client(transport=httpx.MockTransport(handler)),
            "GET",
            "https://example.invalid/",
        )
    assert error.value.status == 504 and "secret" not in str(error.value)
    cache = TTLCache(ttl=30, maxsize=1)
    calls = []

    def fail():
        calls.append(1)
        raise ProviderError("falha")

    for _ in range(2):
        with pytest.raises(ProviderError):
            cache.get_or_load("a", fail)
    assert len(calls) == 2
    assert cache.get_or_load("a", lambda: 3) == cache.get_or_load("a", lambda: 4) == 3


def test_igdb_normalization_and_oauth_reuse():
    calls = []

    def handler(req):
        calls.append(req)
        if req.url.host == "id.twitch.tv":
            assert b"client_secret=private-secret" in req.content
            return httpx.Response(
                200, json={"access_token": "temporary", "expires_in": 3600}
            )
        assert (
            req.headers["client-id"] == "public-id"
            and req.headers["authorization"] == "Bearer temporary"
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 9,
                    "name": "Jogo",
                    "summary": "Resumo",
                    "first_release_date": int(
                        datetime(2020, 1, 1, tzinfo=UTC).timestamp()
                    ),
                    "cover": {"image_id": "co123"},
                    "platforms": [{"name": "PC"}],
                    "genres": [{"name": "RPG"}],
                    "involved_companies": [
                        {"developer": True, "company": {"name": "Estúdio"}}
                    ],
                }
            ],
        )

    provider = IGDBProvider(
        "public-id",
        "private-secret",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.gate.interval = 0
    result = provider.search("jogo", "video_games")[0]
    assert result.metadata["developer"] == "Estúdio" and result.metadata[
        "platforms"
    ] == ["PC"]
    assert result.cover_url.endswith("/co123.jpg")
    assert provider.get_details("9", "video_games").external_id == "9"
    assert sum(req.url.host == "id.twitch.tv" for req in calls) == 1
    assert "private-secret" not in result.model_dump_json()


def test_musicbrainz_release_group_and_football_normalization():
    music = MusicBrainzProvider("ReviewHub/1.0 (https://example.org/contact)")
    album = music.normalize_content(
        {
            "id": "3bd76d40-7f0e-36b7-9348-91a33afee20e",
            "title": "Álbum",
            "first-release-date": "2007-04-17",
            "artist-credit": [{"name": "Artista"}],
            "genres": [{"name": "rock"}],
            "selected_release": {"media": [{"tracks": [{"title": "Faixa"}]}]},
        },
        "music_albums",
    )
    assert (
        album.metadata["tracks"] == ["Faixa"] and album.metadata["artist"] == "Artista"
    )
    assert "/release-group/" in album.cover_url
    football = FootballProvider("test-only")
    match = football.normalize_content(
        {
            "id": 88,
            "status": "FINISHED",
            "homeTeam": {"name": "A"},
            "awayTeam": {"name": "B"},
            "utcDate": "2024-03-12T19:00:00Z",
            "competition": {"name": "Copa"},
            "season": {"startDate": "2024-01-01"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
        "football_matches",
    )
    assert (
        match.metadata["home_score"] == 2
        and match.metadata["match_date"] == "2024-03-12"
    )


def test_lps_blocks_external_provider_and_unknown_domain():
    product = Product.model_validate(
        {
            "name": "Match",
            "color": "#112233",
            "domains": ["football_matches"],
            "features": [
                "identity",
                "catalog",
                "reviews",
                "rating",
                "external_football",
            ],
        }
    )
    assert provider_name("football_matches", product) == "football"
    with pytest.raises(ProviderError) as error:
        provider_name("movies", product)
    assert error.value.status == 404
