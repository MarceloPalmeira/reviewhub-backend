"""Roda Playwright com PostgreSQL temporário e serviços reais, sem Docker."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "reviewhub-frontend"


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait(url, processes):
    for _ in range(200):
        if any(p.poll() is not None for p in processes):
            raise RuntimeError(
                "Um serviço encerrou antes de ficar pronto; veja o log temporário"
            )
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Tempo esgotado: {url}")


def main():
    product_name = sys.argv[1] if len(sys.argv) > 1 else "complete"
    if product_name not in {"cinehub", "matchhub", "complete"}:
        raise SystemExit("Produto deve ser cinehub, matchhub ou complete")
    with tempfile.TemporaryDirectory(prefix="reviewhub-e2e-") as tmp:
        root = Path(tmp)
        pg = root / "pg"
        pg_port = port()
        identity, catalog, reviews, gateway, frontend = [port() for _ in range(5)]
        product = root / "product.json"
        product.write_text(
            json.dumps(
                yaml.safe_load((ROOT / f"products/{product_name}.yaml").read_text())
            )
        )
        subprocess.run(
            [
                "initdb",
                "-D",
                str(pg),
                "-A",
                "trust",
                "-U",
                "reviewhub",
                "--no-locale",
                "-E",
                "UTF8",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "pg_ctl",
                "-D",
                str(pg),
                "-l",
                str(root / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {pg_port}",
                "-w",
                "start",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        processes = []
        try:
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(pg_port),
                    "-U",
                    "reviewhub",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    str(ROOT / "infra/init.sql"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            env = os.environ.copy()
            env.update(
                PRODUCT_CONFIG=str(product),
                JWT_SECRET="test-only-secret-at-least-thirty-two-characters",
                IDENTITY_URL=f"http://127.0.0.1:{identity}",
                CATALOG_URL=f"http://127.0.0.1:{catalog}",
                REVIEWS_URL=f"http://127.0.0.1:{reviews}",
                API_TARGET=f"http://127.0.0.1:{gateway}",
                E2E_BASE_URL=f"http://127.0.0.1:{frontend}",
                E2E_PRODUCT=product_name,
            )
            for name in ("identity", "catalog", "reviews"):
                env[f"{name.upper()}_DATABASE_URL"] = (
                    f"postgresql+psycopg://{name}_service:{name}_dev@127.0.0.1:{pg_port}/{name}"
                )
            with (root / "services.log").open("w+") as log:

                def start(args, cwd=ROOT):
                    processes.append(
                        subprocess.Popen(
                            args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
                        )
                    )

                for name, service_port in (
                    ("identity", identity),
                    ("catalog", catalog),
                    ("reviews", reviews),
                ):
                    start(
                        [
                            "uvicorn",
                            f"services.{name}.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(service_port),
                        ]
                    )
                for service_port in (identity, catalog, reviews):
                    wait(f"http://127.0.0.1:{service_port}/health", processes)
                subprocess.run(
                    [sys.executable, "-m", "services.catalog.seed"],
                    cwd=ROOT,
                    env=env,
                    check=True,
                )
                start(
                    [
                        "uvicorn",
                        "scripts.e2e_gateway:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(gateway),
                    ]
                )
                wait(f"http://127.0.0.1:{gateway}/product.json", processes)
                start(
                    [
                        "npm",
                        "run",
                        "dev",
                        "--",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(frontend),
                        "--strictPort",
                    ],
                    cwd=FRONTEND,
                )
                wait(f"http://127.0.0.1:{frontend}/", processes)
                result = subprocess.run(
                    ["npm", "run", "test:e2e"], cwd=FRONTEND, env=env, check=False
                )
                if result.returncode:
                    log.seek(0)
                    print(log.read(), file=sys.stderr)
                    raise SystemExit(result.returncode)
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                process.wait(timeout=10)
            subprocess.run(
                ["pg_ctl", "-D", str(pg), "-m", "fast", "-w", "stop"],
                check=True,
                stdout=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
