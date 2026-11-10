"""Inicia os serviços locais e o gateway de desenvolvimento, sem Docker."""

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("identity", "catalog", "reviews")


def environment():
    env = os.environ.copy()
    path = ROOT / ".env"
    if path.exists():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                parts = shlex.split(line, comments=True)
            except ValueError as exc:
                raise ValueError(f"Linha {number} inválida em .env") from exc
            if not parts:
                continue
            if len(parts) != 1 or "=" not in parts[0]:
                raise ValueError(f"Linha {number} inválida em .env; use CHAVE=valor")
            key, value = parts[0].split("=", 1)
            if not key.isidentifier():
                raise ValueError(f"Nome de variável inválido na linha {number} de .env")
            env.setdefault(key, value)
    env.setdefault("PRODUCT_CONFIG", str(ROOT / "generated/product.json"))
    for name in SERVICES:
        env.setdefault(
            f"{name.upper()}_DATABASE_URL",
            f"postgresql+psycopg://{name}_service:{name}_dev@127.0.0.1:5432/{name}",
        )
    env.setdefault("IDENTITY_URL", "http://127.0.0.1:8001")
    env.setdefault("CATALOG_URL", "http://127.0.0.1:8002")
    env.setdefault("REVIEWS_URL", "http://127.0.0.1:8003")
    return env


def preflight(env):
    if len(env.get("JWT_SECRET", "")) < 32:
        raise ValueError("Configure JWT_SECRET com pelo menos 32 caracteres no .env.")
    if not Path(env["PRODUCT_CONFIG"]).is_file():
        raise ValueError("Manifesto não encontrado. Execute: mise run lps:cinehub")
    for name in SERVICES:
        variable = f"{name.upper()}_DATABASE_URL"
        url = env[variable]
        if not url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError(f"{variable} deve apontar para um banco PostgreSQL.")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            env[variable] = url
        engine = None
        try:
            engine = create_engine(url, connect_args={"connect_timeout": 3})
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise ValueError(
                f"Não foi possível conectar ao PostgreSQL de {name}. "
                f"Verifique {variable}, o servidor e o provisionamento do banco."
            ) from exc
        finally:
            if engine is not None:
                engine.dispose()


def main():
    try:
        env = environment()
        preflight(env)
    except (OSError, ValueError) as exc:
        print(f"Não foi possível iniciar: {exc}", file=sys.stderr)
        return 1

    commands = [
        ("identity", "services.identity.main:app", "8001"),
        ("catalog", "services.catalog.main:app", "8002"),
        ("reviews", "services.reviews.main:app", "8003"),
        ("gateway", "scripts.e2e_gateway:app", "8080"),
    ]
    processes = []
    try:
        for name, app, port in commands:
            print(f"Iniciando {name} em http://127.0.0.1:{port}", flush=True)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        app,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        port,
                        "--reload",
                    ],
                    cwd=ROOT,
                    env=env,
                    start_new_session=True,
                )
            )
        while True:
            for process, (name, _, _) in zip(processes, commands, strict=True):
                if process.poll() is not None:
                    print(f"{name} encerrou inesperadamente.", file=sys.stderr)
                    return 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nEncerrando serviços locais...", flush=True)
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
