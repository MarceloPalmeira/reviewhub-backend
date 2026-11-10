import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "variant,expected", [("complete", 30), ("cinehub", 12), ("matchhub", 6)]
)
def test_seed_is_idempotent_and_respects_product(tmp_path, variant, expected):
    product = yaml.safe_load(Path(f"products/{variant}.yaml").read_text())
    config = tmp_path / "product.json"
    config.write_text(json.dumps(product))
    database = tmp_path / "catalog.db"
    env = {
        **os.environ,
        "PRODUCT_CONFIG": str(config),
        "CATALOG_DATABASE_URL": f"sqlite:///{database}",
        "JWT_SECRET": "test-secret-at-least-thirty-two-characters",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = [sys.executable, "-m", "services.catalog.seed"]
    subprocess.run(command, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        db.execute(
            "UPDATE contents SET description = ? WHERE id = ?",
            ("preservado", f"demo-{product['domains'][0]}"),
        )
        db.commit()
    subprocess.run(command, env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM contents").fetchone()[0] == expected
        assert {
            row[0] for row in db.execute("SELECT DISTINCT domain FROM contents")
        } == set(product["domains"])
        assert (
            db.execute(
                "SELECT description FROM contents WHERE id = ?",
                (f"demo-{product['domains'][0]}",),
            ).fetchone()[0]
            == "preservado"
        )
