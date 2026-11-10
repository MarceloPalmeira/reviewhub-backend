import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from reviewhub_core.features import Product
from reviewhub_core.plugins import FeatureRegistry, ReviewPolicy


def test_plugins_share_review_policy_and_validate_metadata():
    registry = FeatureRegistry(["movies", "football_matches"])
    movie = registry.get("movies")
    match = registry.get("football_matches")
    assert isinstance(movie.review_policy(), ReviewPolicy)
    assert isinstance(match.review_policy(), ReviewPolicy)
    for plugin in (movie, match):
        plugin.review_policy().validate(4.5, "Excelente")
        with pytest.raises(ValueError):
            plugin.review_policy().validate(4.2, "Excelente")
    assert (
        movie.validate_metadata(
            {"director": "Ana", "duration_minutes": 90, "year": 2020}
        )["director"]
        == "Ana"
    )
    with pytest.raises(ValidationError):
        match.validate_metadata({"home_team": "Azul"})
    with pytest.raises(ValueError, match="não habilitado"):
        registry.get("music_albums")


@pytest.mark.parametrize("filename", ["cinehub", "matchhub", "complete"])
def test_products_validate(filename):
    data = yaml.safe_load(Path(f"products/{filename}.yaml").read_text())
    assert Product.model_validate(data).name


def test_invalid_feature_dependency():
    data = yaml.safe_load(Path("products/matchhub.yaml").read_text())
    data["features"].append("social_feed")
    with pytest.raises(ValidationError, match="social_feed exige user_follows"):
        Product.model_validate(data)


def test_derivation_is_deterministic_and_distinct(tmp_path):
    outputs = []
    for product in ("cinehub", "matchhub"):
        output = tmp_path / f"{product}.json"
        command = [
            sys.executable,
            "-m",
            "reviewhub_core.cli",
            "derive",
            f"products/{product}.yaml",
            "--output",
            str(output),
        ]
        subprocess.run(command, check=True, capture_output=True)
        first = output.read_bytes()
        subprocess.run(command, check=True, capture_output=True)
        assert output.read_bytes() == first
        outputs.append(json.loads(first))
    assert "movies" in outputs[0]["domains"]
    assert outputs[1]["domains"] == ["football_matches"]


def test_feature_metadata_and_specialized_rating():
    plugin = FeatureRegistry(["football_matches"]).get("football_matches")
    metadata = {
        "home_team": "A",
        "away_team": "B",
        "competition": "Copa",
        "match_date": "2024-01-01",
        "home_score": 2,
        "away_score": 1,
    }
    assert (
        plugin.validate_metadata(metadata, ["football_scoreboard"])["home_score"] == 2
    )
    with pytest.raises(ValueError, match="não está habilitada"):
        plugin.validate_metadata(metadata, [])
    assert "home_score" not in plugin.visible_metadata(metadata, [])
    with pytest.raises(ValueError, match="exige os campos"):
        plugin.validate_metadata(
            {k: v for k, v in metadata.items() if not k.endswith("score")},
            ["football_scoreboard"],
        )
    plugin.review_policy().validate(0, "Texto")
    with pytest.raises(ValueError, match="maior que zero"):
        plugin.review_policy(True).validate(0, "Texto")


def test_external_domain_entrypoint(monkeypatch):
    from types import SimpleNamespace

    from reviewhub_core import plugins

    class External(plugins.DomainPlugin):
        identifier = "books"
        schema = plugins.ContentSchema

    monkeypatch.setattr(
        plugins,
        "entry_points",
        lambda **kwargs: [SimpleNamespace(name="books", load=lambda: External)],
    )
    assert plugins.FeatureRegistry(["books"]).get("books").identifier == "books"
