"""Gateway local para testes E2E sem Docker; encaminha chamadas aos serviços reais."""

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.get("/product.json")
def product():
    return Response(
        Path(os.environ["PRODUCT_CONFIG"]).read_text(), media_type="application/json"
    )


SERVICE_URLS = {
    "identity": ("IDENTITY_URL", "http://127.0.0.1:8001"),
    "catalog": ("CATALOG_URL", "http://127.0.0.1:8002"),
    "reviews": ("REVIEWS_URL", "http://127.0.0.1:8003"),
    "recommendations": ("RECOMMENDATIONS_URL", "http://127.0.0.1:8004"),
}


@app.get("/health/{service}")
async def health(service: str):
    if service not in SERVICE_URLS:
        return Response(status_code=404)
    variable, default = SERVICE_URLS[service]
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            upstream = await client.get(f"{os.getenv(variable, default)}/health")
    except httpx.HTTPError:
        return Response(status_code=503)
    return Response(
        upstream.content, upstream.status_code, media_type="application/json"
    )


@app.api_route(
    "/api/v1/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
)
async def proxy(path: str, request: Request):
    if path.startswith(("auth/", "users/")):
        base = os.environ["IDENTITY_URL"]
    elif path.startswith(("contents", "domains", "lists", "external")):
        base = os.environ["CATALOG_URL"]
    elif path.startswith("recommendations"):
        base = os.environ.get("RECOMMENDATIONS_URL", "http://127.0.0.1:8004")
    else:
        base = os.environ["REVIEWS_URL"]
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in {"authorization", "content-type", "accept"}
    }
    async with httpx.AsyncClient(timeout=5) as client:
        upstream = await client.request(
            request.method,
            f"{base}/api/v1/{path}",
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
