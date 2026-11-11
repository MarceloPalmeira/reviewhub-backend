"""Gera manifestos independentes e sem provedores externos para demonstração."""

import json
from pathlib import Path

import yaml

from reviewhub_core.features import Product

EXTERNAL_FEATURES = {"imdb_ratings"}

for name in ("complete", "cinehub", "matchhub"):
    data = yaml.safe_load(Path(f"products/{name}.yaml").read_text(encoding="utf-8"))
    data["features"] = [
        f
        for f in data["features"]
        if not f.startswith("external_") and f not in EXTERNAL_FEATURES
    ]
    product = Product.model_validate(data)
    output = Path("generated/variants") / name / "product.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(product.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
