"""Teste local isolado com PostgreSQL e três processos HTTP; exige initdb, pg_ctl e psql."""

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


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def check(response, expected):
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url}: {response.status_code} {response.text}"
        )
    return response.json() if response.content else None


def main():
    with tempfile.TemporaryDirectory(prefix="reviewhub-pg-") as temp:
        root = Path(temp)
        cluster = root / "pg"
        pg_port = free_port()
        ports = [free_port() for _ in range(3)]
        subprocess.run(
            [
                "initdb",
                "-D",
                str(cluster),
                "-A",
                "trust",
                "-U",
                "reviewhub",
                "--no-locale",
                "-E",
                "UTF8",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "pg_ctl",
                "-D",
                str(cluster),
                "-l",
                str(root / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {pg_port}",
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
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
                    "infra/init.sql",
                ],
                check=True,
                capture_output=True,
            )
            product = root / "product.json"

            def select_product(name):
                product.write_text(
                    json.dumps(
                        yaml.safe_load(Path(f"products/{name}.yaml").read_text())
                    ),
                    encoding="utf-8",
                )

            select_product("complete")
            env = os.environ.copy()
            env.update(
                JWT_SECRET="test-only-secret-at-least-thirty-two-characters",
                PRODUCT_CONFIG=str(product),
                CATALOG_URL=f"http://127.0.0.1:{ports[1]}",
                IDENTITY_URL=f"http://127.0.0.1:{ports[0]}",
            )
            for name in ("identity", "catalog", "reviews"):
                env[f"{name.upper()}_DATABASE_URL"] = (
                    f"postgresql+psycopg://{name}_service:{name}_dev@127.0.0.1:{pg_port}/{name}"
                )
            for name, port in zip(
                ("identity", "catalog", "reviews"), ports, strict=True
            ):
                processes.append(
                    subprocess.Popen(
                        [
                            "uvicorn",
                            f"services.{name}.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(port),
                        ],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )
            for port in ports:
                for _ in range(150):
                    try:
                        if (
                            httpx.get(
                                f"http://127.0.0.1:{port}/health", timeout=0.3
                            ).status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"Serviço {port} não iniciou")
            identity, catalog, reviews = [
                f"http://127.0.0.1:{port}/api/v1" for port in ports
            ]
            users = []
            for name in ("alice", "bruno"):
                user = check(
                    httpx.post(
                        f"{identity}/auth/register",
                        json={
                            "username": name,
                            "display_name": name,
                            "email": f"{name}@example.org",
                            "password": "password123",
                        },
                    ),
                    201,
                )
                login = check(
                    httpx.post(
                        f"{identity}/auth/login",
                        json={"username": name, "password": "password123"},
                    ),
                    200,
                )
                users.append(
                    (user, {"Authorization": f"Bearer {login['access_token']}"})
                )
            alice, bruno = users
            movie = check(
                httpx.post(
                    f"{catalog}/contents",
                    headers=alice[1],
                    json={
                        "domain": "movies",
                        "title": "Filme fictício",
                        "description": "Exemplo",
                        "metadata": {
                            "director": "Ana",
                            "duration_minutes": 90,
                            "year": 2024,
                        },
                    },
                ),
                201,
            )
            review = check(
                httpx.post(
                    f"{reviews}/reviews",
                    headers=alice[1],
                    json={"content_id": movie["id"], "rating": 4.5, "text": "Gostei"},
                ),
                201,
            )
            check(
                httpx.patch(
                    f"{reviews}/reviews/{review['id']}",
                    headers=bruno[1],
                    json={"rating": 3, "text": "Não é minha"},
                ),
                403,
            )
            check(
                httpx.post(
                    f"{identity}/users/{alice[0]['id']}/follow", headers=bruno[1]
                ),
                204,
            )
            assert (
                check(httpx.get(f"{reviews}/feed", headers=bruno[1]), 200)[0]["id"]
                == review["id"]
            )
            check(
                httpx.post(f"{reviews}/reviews/{review['id']}/likes", headers=bruno[1]),
                204,
            )
            assert check(
                httpx.get(f"{reviews}/reviews/{review['id']}/likes", headers=bruno[1]),
                200,
            ) == {"count": 1, "liked": True}
            check(
                httpx.post(
                    f"{reviews}/reviews/{review['id']}/comments",
                    headers=bruno[1],
                    json={"text": "Também gostei"},
                ),
                201,
            )
            assert (
                len(check(httpx.get(f"{reviews}/reviews/{review['id']}/comments"), 200))
                == 1
            )
            assert check(
                httpx.get(
                    f"{reviews}/reviews/stats", params={"content_id": movie["id"]}
                ),
                200,
            ) == {"count": 1, "average": 4.5}
            saved_list = check(
                httpx.post(
                    f"{catalog}/lists", headers=alice[1], json={"name": "Favoritos"}
                ),
                201,
            )
            check(
                httpx.post(
                    f"{catalog}/lists/{saved_list['id']}/items",
                    headers=alice[1],
                    json={"content_id": movie["id"]},
                ),
                201,
            )
            for _ in range(2):
                subprocess.run(
                    [sys.executable, "-m", "services.catalog.seed"],
                    env=env,
                    check=True,
                    capture_output=True,
                )
            assert (
                len(
                    [
                        item
                        for item in check(httpx.get(f"{catalog}/contents"), 200)
                        if item["id"] == "demo-movies"
                    ]
                )
                == 1
            )
            for process in processes:
                process.terminate()
            for process in processes:
                process.wait(timeout=10)
            processes.clear()
            for name, service_port in zip(
                ("identity", "catalog", "reviews"), ports, strict=True
            ):
                processes.append(
                    subprocess.Popen(
                        [
                            "uvicorn",
                            f"services.{name}.main:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(service_port),
                        ],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )
            for service_port in ports:
                for _ in range(150):
                    try:
                        if (
                            httpx.get(
                                f"http://127.0.0.1:{service_port}/health", timeout=0.3
                            ).status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"Serviço {service_port} não reiniciou")
            assert (
                check(
                    httpx.get(f"{catalog}/lists/{saved_list['id']}", headers=alice[1]),
                    200,
                )["items"][0]["id"]
                == movie["id"]
            )
            assert (
                check(httpx.get(f"{reviews}/feed", headers=bruno[1]), 200)[0]["id"]
                == review["id"]
            )
            select_product("matchhub")
            assert check(httpx.get(f"{catalog}/domains"), 200) == ["football_matches"]
            check(httpx.get(f"{catalog}/contents/{movie['id']}"), 404)
            match = check(
                httpx.post(
                    f"{catalog}/contents",
                    headers=bruno[1],
                    json={
                        "domain": "football_matches",
                        "title": "Final fictícia",
                        "description": "Exemplo",
                        "metadata": {
                            "home_team": "Azul",
                            "away_team": "Verde",
                            "competition": "Copa",
                            "match_date": "2024-01-01",
                            "home_score": 2,
                            "away_score": 1,
                        },
                    },
                ),
                201,
            )
            assert match["metadata"]["home_score"] == 2
            check(
                httpx.post(
                    f"{reviews}/reviews",
                    headers=bruno[1],
                    json={
                        "content_id": match["id"],
                        "rating": 3.5,
                        "text": "Boa partida",
                    },
                ),
                201,
            )
            check(httpx.get(f"{reviews}/feed", headers=bruno[1]), 404)
            check(
                httpx.post(f"{reviews}/reviews/{review['id']}/likes", headers=bruno[1]),
                404,
            )
            select_product("cinehub")
            assert check(httpx.get(f"{catalog}/domains"), 200) == ["movies", "series"]
            check(httpx.get(f"{catalog}/contents/{movie['id']}"), 200)
            check(httpx.get(f"{catalog}/contents/{match['id']}"), 404)
            print(
                "PostgreSQL: migrations, autenticação, reviews, seguidores, feed, curtidas, comentários e variabilidade OK"
            )
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                process.wait(timeout=10)
            subprocess.run(
                ["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    main()
