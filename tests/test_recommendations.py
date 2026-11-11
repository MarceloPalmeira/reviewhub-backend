import json

import pytest
from fastapi.testclient import TestClient

from services.common import token_for
from services.recommendations import main as rec

MOVIES = [
    {
        "id": "inception",
        "domain": "movies",
        "title": "Inception",
        "genres": ["Sci-Fi", "Action"],
        "metadata": {"director": "Christopher Nolan"},
    },
    {
        "id": "interstellar",
        "domain": "movies",
        "title": "Interstellar",
        "genres": ["Sci-Fi", "Drama"],
        "metadata": {"director": "Christopher Nolan"},
    },
    {
        "id": "la-la-land",
        "domain": "movies",
        "title": "La La Land",
        "genres": ["Musical", "Romance"],
        "metadata": {"director": "Damien Chazelle"},
    },
    {
        "id": "notebook",
        "domain": "movies",
        "title": "The Notebook",
        "genres": ["Romance"],
        "metadata": {},
    },
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    product = tmp_path / "product.json"
    product.write_text(
        json.dumps(
            {
                "name": "CineHub",
                "color": "#aabbcc",
                "domains": ["movies"],
                "features": [
                    "identity",
                    "catalog",
                    "reviews",
                    "rating",
                    "recommendations",
                ],
            }
        )
    )
    monkeypatch.setenv("PRODUCT_CONFIG", str(product))
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-thirty-two-characters")
    state = {"history": [], "recent": []}

    def reviews_api(path, params=None):
        if params.get("author_id"):
            return state["history"]
        return state["recent"]

    def catalog_api(path, params=None):
        if isinstance(params, list):
            ids = {v for k, v in params if k == "content_id"}
            return [m for m in MOVIES if m["id"] in ids]
        return MOVIES

    monkeypatch.setattr(rec, "reviews_api", reviews_api)
    monkeypatch.setattr(rec, "catalog_api", catalog_api)
    with TestClient(rec.app) as test_client:
        yield test_client, state, product


def auth(user="u1"):
    return {"Authorization": f"Bearer {token_for(user)}"}


def test_recommends_from_history_and_excludes_seen(client):
    test_client, state, _ = client
    state["history"] = [
        {"content_id": "inception", "rating": 5.0},
        {"content_id": "notebook", "rating": 1.0},
    ]
    body = test_client.get("/api/v1/recommendations", headers=auth()).json()
    ids = [item["content"]["id"] for item in body["items"]]
    assert body["based_on"] == 2
    assert "inception" not in ids and "notebook" not in ids
    assert ids[0] == "interstellar"  # mesmo diretor e gênero
    assert body["items"][0]["reason"] in {
        "Porque você curtiu Christopher Nolan",
        "Porque você curtiu Sci-Fi",
    }
    # La La Land (Romance, avaliado mal) fica abaixo
    assert ids.index("la-la-land") > ids.index("interstellar")


def test_cold_start_uses_popularity(client):
    test_client, state, _ = client
    state["recent"] = [
        {"content_id": "la-la-land", "rating": 5.0},
        {"content_id": "la-la-land", "rating": 4.5},
    ]
    body = test_client.get("/api/v1/recommendations", headers=auth()).json()
    assert body["based_on"] == 0
    assert body["items"][0]["content"]["id"] == "la-la-land"
    assert body["items"][0]["reason"] == "Popular na comunidade"


def test_requires_auth_and_feature(client):
    test_client, _, product = client
    assert test_client.get("/api/v1/recommendations").status_code == 401
    config = json.loads(product.read_text())
    config["features"].remove("recommendations")
    product.write_text(json.dumps(config))
    assert test_client.get("/api/v1/recommendations", headers=auth()).status_code == 404
    assert test_client.get("/health").json() == {"status": "ok"}


def test_football_tags_use_teams_and_competition():
    found = rec.tags(
        {
            "genres": [],
            "metadata": {
                "home_team": "CR Flamengo",
                "away_team": "Santos FC",
                "competition": "Brasileirão Série A",
            },
        }
    )
    assert set(found.values()) == {"CR Flamengo", "Santos FC", "Brasileirão Série A"}


def test_diversify_alternates_reasons():
    results = [
        {"score": 10, "reason": "A", "content": {"id": "1"}},
        {"score": 9.9, "reason": "A", "content": {"id": "2"}},
        {"score": 9.8, "reason": "A", "content": {"id": "3"}},
        {"score": 9.0, "reason": "B", "content": {"id": "4"}},
    ]
    ordered = [r["content"]["id"] for r in rec.diversify(results, 3)]
    assert ordered == ["1", "4", "2"]
