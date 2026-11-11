import importlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def clients(tmp_path, monkeypatch):
    product = tmp_path / "product.json"
    product.write_text(
        json.dumps(
            {
                "name": "CineHub",
                "color": "#aabbcc",
                "domains": ["movies", "series"],
                "features": [
                    "identity",
                    "catalog",
                    "reviews",
                    "rating",
                    "comments",
                    "spoiler_control",
                ],
            }
        )
    )
    monkeypatch.setenv("PRODUCT_CONFIG", str(product))
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-thirty-two-characters")
    for name in ("IDENTITY", "CATALOG", "REVIEWS"):
        monkeypatch.setenv(f"{name}_DATABASE_URL", f"sqlite:///{tmp_path / name}.db")
    from services.catalog import main as catalog_module
    from services.identity import main as identity_module
    from services.reviews import main as review_module

    importlib.reload(catalog_module)
    importlib.reload(identity_module)
    importlib.reload(review_module)
    catalog = catalog_module.app
    identity = identity_module.app

    with (
        TestClient(identity) as users,
        TestClient(catalog) as contents,
        TestClient(review_module.app) as reviews,
    ):
        monkeypatch.setattr(
            review_module,
            "catalog_item",
            lambda content_id: contents.get(f"/api/v1/contents/{content_id}").json(),
        )
        yield users, contents, reviews


def test_registration_content_review_and_authorization(clients):
    users, contents, reviews = clients
    registered = users.post(
        "/api/v1/auth/register",
        json={
            "username": "maria",
            "display_name": "Maria",
            "email": "maria@example.org",
            "password": "secret123",
        },
    )
    assert registered.status_code == 201
    assert (
        users.post(
            "/api/v1/auth/login", json={"username": "maria", "password": "wrong"}
        ).status_code
        == 401
    )
    login = users.post(
        "/api/v1/auth/login", json={"username": "maria", "password": "secret123"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    movie = contents.post(
        "/api/v1/contents",
        headers=headers,
        json={
            "domain": "movies",
            "title": "Filme fictício",
            "description": "Exemplo",
            "metadata": {"director": "Ana", "duration_minutes": 90, "year": 2024},
        },
    )
    assert movie.status_code == 201
    content_id = movie.json()["id"]
    assert (
        contents.post(
            "/api/v1/contents",
            headers=headers,
            json={
                "domain": "football_matches",
                "title": "Partida",
                "description": "",
                "metadata": {},
            },
        ).status_code
        == 422
    )
    payload = {
        "content_id": content_id,
        "rating": 4.5,
        "text": "Gostei",
        "spoiler": False,
    }
    review = reviews.post("/api/v1/reviews", headers=headers, json=payload)
    assert review.status_code == 201
    assert (
        reviews.post("/api/v1/reviews", headers=headers, json=payload).status_code
        == 409
    )
    assert (
        reviews.get(
            "/api/v1/reviews", params={"author_id": login["user"]["id"]}
        ).json()[0]["text"]
        == "Gostei"
    )
    assert (
        reviews.patch(
            f"/api/v1/reviews/{review.json()['id']}",
            headers=headers,
            json={"rating": 3, "text": "Editada"},
        ).status_code
        == 200
    )
    assert (
        reviews.post(
            f"/api/v1/reviews/{review.json()['id']}/likes", headers=headers
        ).status_code
        == 404
    )
    assert (
        users.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    expired = jwt.encode(
        {"sub": login["user"]["id"], "exp": datetime.now(UTC) - timedelta(seconds=1)},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    assert (
        users.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"}
        ).status_code
        == 401
    )
    allowed = users.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = users.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert blocked.status_code == 400


def test_social_features_and_disabled_routes(clients, monkeypatch):
    users, contents, reviews = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["features"] += ["review_likes", "user_follows", "social_feed"]
    path.write_text(json.dumps(config))
    from services.reviews import main as review_module

    people = []
    for name in ("alice", "bruno"):
        assert (
            users.post(
                "/api/v1/auth/register",
                json={
                    "username": name,
                    "display_name": name,
                    "email": f"{name}@example.org",
                    "password": "secret123",
                },
            ).status_code
            == 201
        )
        result = users.post(
            "/api/v1/auth/login", json={"username": name, "password": "secret123"}
        ).json()
        people.append(
            (
                result["user"]["id"],
                {"Authorization": f"Bearer {result['access_token']}"},
            )
        )
    alice, bruno = people
    movie = contents.post(
        "/api/v1/contents",
        headers=alice[1],
        json={
            "domain": "movies",
            "title": "Filme",
            "description": "",
            "metadata": {"director": "Ana", "duration_minutes": 90, "year": 2020},
        },
    ).json()
    review = reviews.post(
        "/api/v1/reviews",
        headers=alice[1],
        json={"content_id": movie["id"], "rating": 4, "text": "Bom"},
    ).json()
    url = f"/api/v1/reviews/{review['id']}"
    assert (
        users.post(f"/api/v1/users/{alice[0]}/follow", headers=bruno[1]).status_code
        == 204
    )
    assert users.get(f"/api/v1/users/{alice[0]}/social").json()["followers"] == 1
    assert (
        reviews.patch(
            url, headers=bruno[1], json={"rating": 3, "text": "Não autorizada"}
        ).status_code
        == 403
    )
    assert reviews.post(f"{url}/likes", headers=bruno[1]).status_code == 204
    assert reviews.get(f"{url}/likes", headers=bruno[1]).json() == {
        "count": 1,
        "liked": True,
    }
    assert (
        reviews.post(
            f"{url}/comments", headers=bruno[1], json={"text": "Concordo"}
        ).status_code
        == 201
    )
    assert reviews.get(f"{url}/comments").json()[0]["text"] == "Concordo"
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: [alice[0]])
    monkeypatch.setattr(review_module.httpx, "get", lambda *args, **kwargs: response)
    assert reviews.get("/api/v1/feed", headers=bruno[1]).json()[0]["id"] == review["id"]
    assert reviews.get(
        "/api/v1/reviews/stats", params={"content_id": movie["id"]}
    ).json() == {"count": 1, "average": 4.0}
    config["features"] = [
        x
        for x in config["features"]
        if x not in ("review_likes", "user_follows", "social_feed", "comments")
    ]
    path.write_text(json.dumps(config))
    assert reviews.get("/api/v1/feed", headers=bruno[1]).status_code == 404
    assert reviews.get(f"{url}/likes", headers=bruno[1]).status_code == 404
    assert reviews.get(f"{url}/comments").status_code == 404
    assert users.get(f"/api/v1/users/{alice[0]}/social").status_code == 404


def test_custom_lists_ownership_and_feature_gate(clients):
    users, catalog, _ = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["features"].append("custom_lists")
    path.write_text(json.dumps(config))
    headers = []
    for name in ("listaana", "listabia"):
        assert (
            users.post(
                "/api/v1/auth/register",
                json={
                    "username": name,
                    "display_name": name,
                    "email": f"{name}@example.org",
                    "password": "password123",
                },
            ).status_code
            == 201
        )
        token = users.post(
            "/api/v1/auth/login", json={"username": name, "password": "password123"}
        ).json()["access_token"]
        headers.append({"Authorization": f"Bearer {token}"})
    owner, other = headers
    movie = catalog.post(
        "/api/v1/contents",
        headers=owner,
        json={
            "domain": "movies",
            "title": "Filme",
            "description": "",
            "metadata": {"director": "Ana", "duration_minutes": 90, "year": 2024},
        },
    ).json()
    created = catalog.post("/api/v1/lists", headers=owner, json={"name": "Favoritos"})
    assert created.status_code == 201
    url = f"/api/v1/lists/{created.json()['id']}"
    assert catalog.get(url, headers=other).status_code == 403
    assert catalog.patch(url, headers=other, json={"name": "Roubo"}).status_code == 403
    assert (
        catalog.post(
            f"{url}/items", headers=other, json={"content_id": movie["id"]}
        ).status_code
        == 403
    )
    assert (
        catalog.post(
            f"{url}/items", headers=owner, json={"content_id": "missing"}
        ).status_code
        == 404
    )
    assert (
        catalog.post(
            f"{url}/items", headers=owner, json={"content_id": movie["id"]}
        ).status_code
        == 201
    )
    assert (
        catalog.post(
            f"{url}/items", headers=owner, json={"content_id": movie["id"]}
        ).status_code
        == 409
    )
    assert catalog.get(url, headers=owner).json()["items"][0]["id"] == movie["id"]
    assert (
        catalog.patch(url, headers=owner, json={"name": "Nova lista"}).json()["name"]
        == "Nova lista"
    )
    assert (
        catalog.delete(f"{url}/items/{movie['id']}", headers=owner).status_code == 204
    )
    assert catalog.delete(url, headers=other).status_code == 403
    assert catalog.delete(url, headers=owner).status_code == 204
    config["features"].remove("custom_lists")
    path.write_text(json.dumps(config))
    assert catalog.get("/api/v1/lists", headers=owner).status_code == 404
    assert (
        catalog.post("/api/v1/lists", headers=owner, json={"name": "Não"}).status_code
        == 404
    )


def test_external_import_reuses_id_and_batch_reviews(clients, monkeypatch):
    import httpx

    from services.catalog import external_routes
    from services.catalog.providers.tmdb import TMDBProvider

    users, catalog, reviews = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["features"].append("external_tmdb")
    path.write_text(json.dumps(config))
    calls = []

    def handler(req):
        calls.append(req)
        if req.url.path.endswith("/search/movie"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 123, "title": "Filme real", "release_date": "2024-01-01"}
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 123,
                "title": "Filme real",
                "release_date": "2024-01-01",
                "runtime": 90,
                "credits": {"crew": [{"job": "Director", "name": "Ana"}], "cast": []},
            },
        )

    provider = TMDBProvider(
        "private-test-token", httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.gate.interval = 0
    monkeypatch.setattr(external_routes, "configured_provider", lambda name: provider)
    assert (
        users.post(
            "/api/v1/auth/register",
            json={
                "username": "pessoa",
                "display_name": "Pessoa",
                "email": "pessoa@example.org",
                "password": "password123",
            },
        ).status_code
        == 201
    )
    login = users.post(
        "/api/v1/auth/login", json={"username": "pessoa", "password": "password123"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    result = catalog.get(
        "/api/v1/external/search", params={"domain": "movies", "q": "filme"}
    )
    assert (
        result.status_code == 200
        and result.json()["results"][0]["external_id"] == "123"
    )
    assert "private-test-token" not in result.text
    first = catalog.post(
        "/api/v1/external/import",
        headers=headers,
        json={"domain": "movies", "external_id": "123"},
    )
    second = catalog.post(
        "/api/v1/external/import",
        headers=headers,
        json={"domain": "movies", "external_id": "123"},
    )
    assert first.status_code == 200 and first.json()["id"] == second.json()["id"]
    assert len(calls) == 2
    content_id = first.json()["id"]
    review = reviews.post(
        "/api/v1/reviews",
        headers=headers,
        json={"content_id": content_id, "rating": 4.5, "text": "Muito bom"},
    )
    assert review.status_code == 201
    stats = reviews.get(
        "/api/v1/reviews/stats/batch",
        params=[("content_id", content_id), ("content_id", "outro")],
    ).json()
    assert stats[content_id] == {"count": 1, "average": 4.5} and stats["outro"] == {
        "count": 0,
        "average": None,
    }
    assert (
        catalog.get(
            "/api/v1/external/search",
            params={"domain": "football_matches", "q": "copa"},
        ).status_code
        == 404
    )
    config["features"].remove("external_tmdb")
    path.write_text(json.dumps(config))
    assert (
        catalog.post(
            "/api/v1/external/import",
            headers=headers,
            json={"domain": "movies", "external_id": "123"},
        ).status_code
        == 404
    )


def test_imdb_ratings_feature_gate_and_matching(clients, monkeypatch):
    import httpx

    from services.catalog import imdb_routes
    from services.catalog.providers.omdb import OMDbProvider
    from services.catalog.providers.tmdb import TMDBProvider

    users, catalog, _ = clients
    users.post(
        "/api/v1/auth/register",
        json={
            "username": "cinefila",
            "display_name": "Cinéfila",
            "email": "cinefila@example.org",
            "password": "password123",
        },
    )
    token = users.post(
        "/api/v1/auth/login", json={"username": "cinefila", "password": "password123"}
    ).json()["access_token"]
    movie = catalog.post(
        "/api/v1/contents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "domain": "movies",
            "title": "Intolerance",
            "description": "",
            "metadata": {
                "director": "D. W. Griffith",
                "duration_minutes": 163,
                "year": 1916,
            },
        },
    ).json()
    url = f"/api/v1/contents/{movie['id']}/imdb"
    assert catalog.get(url).status_code == 404

    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["features"].append("imdb_ratings")
    path.write_text(json.dumps(config))
    monkeypatch.setattr(imdb_routes, "configured_provider", lambda name: None)
    assert catalog.get(url).json() == {"configured": False, "found": False}

    omdb_calls = []

    def omdb_handler(req):
        omdb_calls.append(dict(req.url.params))
        return httpx.Response(
            200,
            json={
                "Response": "True",
                "imdbID": "tt0006864",
                "imdbRating": "7.7",
                "imdbVotes": "16,112",
            },
        )

    omdb = OMDbProvider(
        "omdb-key", httpx.Client(transport=httpx.MockTransport(omdb_handler))
    )
    omdb.gate.interval = 0
    tmdb = TMDBProvider(
        "tmdb-token",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"imdb_id": "tt0006864"})
            )
        ),
    )
    tmdb.gate.interval = 0
    providers = {"omdb": omdb, "tmdb": tmdb}
    monkeypatch.setattr(imdb_routes, "configured_provider", providers.get)
    body = catalog.get(url).json()
    assert body["found"] and body["matched_by"] == "title"
    assert body["rating"] == 7.7 and body["votes"] == 16112
    assert omdb_calls[-1]["t"] == "Intolerance" and omdb_calls[-1]["y"] == "1916"
    assert "omdb-key" not in json.dumps(body)

    from services.catalog import main as catalog_module

    with catalog_module.Session() as db:
        row = db.get(catalog_module.Content, movie["id"])
        row.external_provider, row.external_id = "tmdb", "3060"
        db.commit()
    body = catalog.get(url).json()
    assert body["matched_by"] == "imdb_id" and omdb_calls[-1]["i"] == "tt0006864"


def test_seed_omdb_is_idempotent_and_links_imdb(clients, monkeypatch):
    from reviewhub_core.external import ExternalContent
    from services.catalog import imdb_routes, seed_omdb

    _, catalog, _ = clients

    class FakeOMDb:
        calls = 0

        def get_details(self, imdb_id, domain):
            FakeOMDb.calls += 1
            return ExternalContent(
                provider="omdb",
                external_id=imdb_id,
                domain=domain,
                title=f"Filme {imdb_id}",
                description="Sinopse",
                cover_url="https://example.org/poster.jpg",
                release_date="2010-07-16",
                genres=["Drama"],
                metadata={"director": "Ana", "duration_minutes": 100, "year": 2010},
            )

        def ratings(self, domain, imdb_id=None, title=None, year=None):
            assert imdb_id == "tt0000002" and title is None
            return {"imdb_id": imdb_id, "rating": 8.0, "votes": 10, "url": "u"}

    ids = ["tt0000001", "tt0000002"]
    assert seed_omdb.main(FakeOMDb(), ids) == 0
    assert seed_omdb.main(FakeOMDb(), ids) == 0
    assert FakeOMDb.calls == 2
    movies = catalog.get("/api/v1/contents", params={"q": "Filme tt"}).json()
    assert sorted(m["external_id"] for m in movies) == ids
    assert {m["external_provider"] for m in movies} == {"omdb"}

    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["features"].append("imdb_ratings")
    path.write_text(json.dumps(config))
    monkeypatch.setattr(
        imdb_routes,
        "configured_provider",
        lambda name: FakeOMDb() if name == "omdb" else None,
    )
    body = catalog.get("/api/v1/contents/omdb-movies-tt0000002/imdb").json()
    assert body["matched_by"] == "imdb_id" and body["rating"] == 8.0


def test_seed_football_is_idempotent_and_hides_disabled_scoreboard(clients):
    from reviewhub_core.external import ExternalContent
    from services.catalog import seed_football

    _, catalog, _ = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["domains"] = ["football_matches"]
    path.write_text(json.dumps(config))

    class FakeFootball:
        def competition_matches(self, code, season):
            assert (code, season) == ("WC", 2026)
            return [
                ExternalContent(
                    provider="football",
                    external_id=str(n),
                    domain="football_matches",
                    title=f"Time {n} × Rival",
                    description="Copa do Mundo FIFA · Final",
                    release_date="2026-07-19",
                    metadata={
                        "home_team": f"Time {n}",
                        "away_team": "Rival",
                        "home_score": 1,
                        "away_score": 0,
                        "competition": "Copa do Mundo FIFA",
                        "match_date": "2026-07-19",
                    },
                )
                for n in (1, 2)
            ]

    assert seed_football.parse(["bsa:2025", "WC"]) == [("BSA", 2025), ("WC", None)]
    assert seed_football.main(FakeFootball(), [("WC", 2026)]) == 0
    assert seed_football.main(FakeFootball(), [("WC", 2026)]) == 0
    items = catalog.get("/api/v1/contents", params={"q": "Rival"}).json()
    assert len(items) == 2 and {i["external_provider"] for i in items} == {"football"}
    # football_scoreboard desligada: placar não é gravado nem exibido
    assert all("home_score" not in i["metadata"] for i in items)


def test_seed_music_retries_rate_limit_and_is_idempotent(clients):
    from reviewhub_core.external import ExternalContent
    from services.catalog import seed_music
    from services.catalog.providers.base import ProviderError

    _, catalog, _ = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["domains"] = ["music_albums"]
    path.write_text(json.dumps(config))
    mbid = "9162580e-5df4-32de-80cc-f45a8d8a9b1d"

    class FakeMusicBrainz:
        calls = 0

        def get_details(self, external_id, domain):
            FakeMusicBrainz.calls += 1
            if FakeMusicBrainz.calls == 1:
                raise ProviderError("Provedor externo indisponível", 503)
            return ExternalContent(
                provider="musicbrainz",
                external_id=external_id,
                domain=domain,
                title="Abbey Road",
                cover_url="https://coverartarchive.org/x/front-500",
                release_date="1969-09-26",
                genres=["rock"],
                metadata={
                    "artist": "The Beatles",
                    "genre": "rock",
                    "year": 1969,
                    "tracks": ["Come Together"],
                },
            )

    assert seed_music.main(FakeMusicBrainz(), [mbid], wait=0) == 0
    assert seed_music.main(FakeMusicBrainz(), [mbid], wait=0) == 0
    assert FakeMusicBrainz.calls == 2
    (album,) = catalog.get("/api/v1/contents", params={"q": "Abbey"}).json()
    assert album["external_id"] == mbid
    # track_listing desligada: faixas não são gravadas
    assert album["metadata"] == {"artist": "The Beatles", "genre": "rock", "year": 1969}


def test_seed_games_batches_and_reports_missing(clients):
    from reviewhub_core.external import ExternalContent
    from services.catalog import seed_games

    _, catalog, _ = clients
    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["domains"] = ["video_games"]
    path.write_text(json.dumps(config))

    batches = []

    class FakeIGDB:
        def get_many(self, ids, domain):
            batches.append(list(ids))
            return [
                ExternalContent(
                    provider="igdb",
                    external_id=i,
                    domain=domain,
                    title=f"Jogo {i}",
                    metadata={
                        "developer": "Estúdio",
                        "genre": "RPG",
                        "year": 2015,
                        "platforms": ["PC"],
                    },
                )
                for i in ids
                if i != "3"
            ]

    assert seed_games.main(FakeIGDB(), [1, 2, 3]) == 2  # 3 não existe
    assert seed_games.main(FakeIGDB(), [1, 2, 3]) == 2
    assert batches == [["1", "2", "3"], ["3"]]
    games = catalog.get("/api/v1/contents", params={"q": "Jogo"}).json()
    assert sorted(g["external_id"] for g in games) == ["1", "2"]
    # game_platforms desligada: plataformas não são gravadas
    assert all("platforms" not in g["metadata"] for g in games)


def test_seed_music_tolerates_concurrent_insert(clients, monkeypatch):
    from reviewhub_core.external import ExternalContent
    from services.catalog import main as catalog_module
    from services.catalog import seed_music

    path = Path(os.environ["PRODUCT_CONFIG"])
    config = json.loads(path.read_text())
    config["domains"] = ["music_albums"]
    path.write_text(json.dumps(config))
    mbid = "9162580e-5df4-32de-80cc-f45a8d8a9b1d"

    class Racing:
        def get_details(self, external_id, domain):
            # Simula outra execução gravando o mesmo álbum neste intervalo.
            with catalog_module.Session() as other:
                other.add(
                    catalog_module.Content(
                        id=f"musicbrainz-{external_id}",
                        domain=domain,
                        title="Abbey Road",
                        description="",
                        metadata_json={},
                        external_provider="musicbrainz",
                        external_id=external_id,
                    )
                )
                other.commit()
            return ExternalContent(
                provider="musicbrainz",
                external_id=external_id,
                domain=domain,
                title="Abbey Road",
                metadata={"artist": "The Beatles"},
            )

    assert seed_music.main(Racing(), [mbid], wait=0) == 0
