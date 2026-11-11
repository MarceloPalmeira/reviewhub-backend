"""Recommendation Service: recomendações a partir do histórico do usuário.

Serviço sem banco próprio. Lê o histórico do usuário no Reviews Service e os
conteúdos no Catalog Service, sempre por HTTP, e calcula as recomendações em
memória a cada requisição. Assim não duplica dados de outros serviços e
continua independente para implantar e escalar.

Algoritmo (filtragem baseada em conteúdo + popularidade):

1. Perfil: para cada review do usuário, as *tags* do conteúdo (gêneros,
   direção, artista, desenvolvedora, times, competição) recebem o peso
   ``nota - 2,5``; notas altas aproximam, notas baixas afastam. Criadores
   (direção, artista, desenvolvedora, times) valem o dobro dos gêneros, por
   serem mais específicos. O domínio avaliado também ganha peso.
2. Candidatos: conteúdos dos domínios habilitados que o usuário ainda não
   avaliou.
3. Pontuação: soma dos pesos das tags do candidato (normalizada), mais a
   preferência pelo domínio e um bônus de popularidade calculado com as
   reviews recentes da comunidade.
4. Diversidade: cada repetição de um mesmo motivo reduz a pontuação dos
   próximos itens com ele, para a lista não ficar monotemática.
5. Sem histórico (*cold start*): ordena por popularidade e novidade.

Cada item traz o motivo da recomendação, exibido na interface.
"""

import math
import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query

from services.common import configure_app, current_user, enabled, product, secret


@asynccontextmanager
async def lifespan(app):
    product()
    secret()
    yield


app = FastAPI(
    title="ReviewHub Recommendations",
    description="Recomenda conteúdos com base no histórico de reviews do usuário.",
    lifespan=lifespan,
)
configure_app(app)

NEUTRAL = 2.5  # ponto médio da escala 0–5
CANDIDATES_PER_DOMAIN = 100
CREATOR_BOOST = 2.0  # peso extra de diretor, artista, desenvolvedora e times
DIVERSITY_DECAY = 0.8  # penalidade por repetir o mesmo motivo


def _get(base_env: str, default: str, path: str, params=None):
    url = f"{os.getenv(base_env, default)}{path}"
    try:
        response = httpx.get(url, params=params, timeout=3)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Serviço dependente indisponível") from exc


def reviews_api(path, params=None):
    return _get("REVIEWS_URL", "http://localhost:8003", path, params)


def catalog_api(path, params=None):
    return _get("CATALOG_URL", "http://localhost:8002", path, params)


def tags(content: dict) -> dict[str, str]:
    """Tags normalizadas do conteúdo -> rótulo legível usado no motivo."""
    meta = content.get("metadata") or {}
    found: dict[str, str] = {}
    genres = list(content.get("genres") or [])
    if isinstance(meta.get("genre"), str):
        genres += [g.strip() for g in meta["genre"].replace(";", ",").split(",")]
    for genre in genres:
        if genre:
            found[f"genre:{genre.casefold()}"] = genre
    for key in ("director", "artist", "developer", "competition"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            found[f"{key}:{value.casefold()}"] = value
    for key in ("home_team", "away_team"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            found[f"team:{value.casefold()}"] = value
    return found


def build_profile(history: list[dict], contents: dict[str, dict]):
    weights: dict[str, float] = defaultdict(float)
    labels: dict[str, str] = {}
    domains: dict[str, float] = defaultdict(float)
    for review in history:
        content = contents.get(review["content_id"])
        if not content:
            continue
        delta = float(review["rating"]) - NEUTRAL
        domains[content["domain"]] += 1 + delta / NEUTRAL
        for key, label in tags(content).items():
            weights[key] += delta
            labels[key] = label
    return weights, labels, domains


def popularity(recent: list[dict]):
    counts, totals = Counter(), defaultdict(float)
    for review in recent:
        counts[review["content_id"]] += 1
        totals[review["content_id"]] += float(review["rating"])
    return {
        cid: (totals[cid] / counts[cid]) * math.log1p(counts[cid]) / NEUTRAL
        for cid in counts
    }


def recommend(history, contents, candidates, popular, limit):
    weights, labels, domains = build_profile(history, contents)
    seen = {review["content_id"] for review in history}
    top_domain = max(domains.values(), default=0) or 1
    results = []
    for item in candidates:
        if item["id"] in seen:
            continue
        item_tags = tags(item)
        # Criadores (diretor, artista, desenvolvedora, times) são mais
        # específicos que gêneros; tags mal avaliadas também pesam, para baixo.
        weighted = [
            (weights[k] * (1 if k.startswith("genre:") else CREATOR_BOOST), k)
            for k in item_tags
            if weights.get(k)
        ]
        matches = [(w, k) for w, k in weighted if w > 0]
        affinity = sum(w for w, _ in weighted) / math.sqrt(len(item_tags) or 1)
        score = (
            affinity
            + 0.5 * max(domains.get(item["domain"], 0), 0) / top_domain
            + 0.3 * popular.get(item["id"], 0)
        )
        if matches:
            best = max(matches)[1]
            reason = f"Porque você curtiu {labels[best]}"
        elif item["id"] in popular:
            reason = "Popular na comunidade"
        else:
            reason = "Novidade no catálogo"
        results.append({"score": round(score, 4), "reason": reason, "content": item})
    return diversify(results, limit)


def diversify(results, limit, decay=DIVERSITY_DECAY):
    """Reordena para variar os motivos: cada repetição de um mesmo motivo
    multiplica a pontuação dos próximos itens com ele por ``decay``."""
    pool = sorted(results, key=lambda r: r["score"], reverse=True)
    used: Counter = Counter()
    chosen = []
    while pool and len(chosen) < limit:
        best = max(pool, key=lambda r: r["score"] * decay ** used[r["reason"]])
        pool.remove(best)
        used[best["reason"]] += 1
        chosen.append(best)
    return chosen


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/recommendations")
def recommendations(
    user_id: str = Depends(current_user),
    domain: str | None = None,
    limit: int = Query(12, ge=1, le=50),
):
    """Recomendações para o usuário autenticado.

    - `domain` (opcional): restringe a um domínio habilitado.
    - Resposta: `{"based_on": n_reviews, "items": [{score, reason, content}]}`.
    - 404 se a feature `recommendations` estiver desligada no produto.
    """
    enabled("recommendations")
    domains = product().domains
    if domain and domain not in domains:
        raise HTTPException(404, "Domínio indisponível")
    history = reviews_api("/api/v1/reviews", {"author_id": user_id, "limit": 100})
    contents = {}
    if history:
        ids = [("content_id", r["content_id"]) for r in history]
        found = catalog_api("/api/v1/contents", [*ids, ("limit", 100)])
        contents = {c["id"]: c for c in found}
    names = [domain] if domain else domains
    # Uma chamada por domínio, em paralelo, para não somar as latências.
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        pages = pool.map(
            lambda name: catalog_api(
                "/api/v1/contents", {"domain": name, "limit": CANDIDATES_PER_DOMAIN}
            ),
            names,
        )
        candidates = [item for page in pages for item in page]
    recent = reviews_api("/api/v1/reviews", {"limit": 100})
    return {
        "based_on": len(history),
        "items": recommend(history, contents, candidates, popularity(recent), limit),
    }
