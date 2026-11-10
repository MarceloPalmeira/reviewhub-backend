import pytest

from scripts import dev_local


def test_environment_reads_dotenv_without_overriding_exported_values(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(dev_local, "ROOT", tmp_path)
    monkeypatch.setenv("JWT_SECRET", "valor-exportado")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        'JWT_SECRET=valor-do-arquivo\nCATALOG_DATABASE_URL="postgresql://localhost/catalog"\n',
        encoding="utf-8",
    )
    env = dev_local.environment()
    assert env["JWT_SECRET"] == "valor-exportado"
    assert env["CATALOG_DATABASE_URL"] == "postgresql://localhost/catalog"
    assert env["PRODUCT_CONFIG"] == str(tmp_path / "generated/product.json")


def test_preflight_rejects_non_postgresql_without_connecting(tmp_path):
    manifest = tmp_path / "product.json"
    manifest.write_text("{}", encoding="utf-8")
    env = {
        "JWT_SECRET": "x" * 32,
        "PRODUCT_CONFIG": str(manifest),
        "IDENTITY_DATABASE_URL": "sqlite:///identity.db",
    }
    with pytest.raises(ValueError, match="PostgreSQL"):
        dev_local.preflight(env)
