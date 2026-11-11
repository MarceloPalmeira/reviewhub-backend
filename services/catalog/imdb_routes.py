"""Notas do IMDb (via OMDb) para filmes e séries do catálogo."""

from fastapi import APIRouter, HTTPException

from services.catalog.providers.base import ProviderError
from services.catalog.providers.omdb import KINDS
from services.catalog.providers.registry import configured_provider
from services.common import enabled, product


def _year(item):
    year = (item.metadata_json or {}).get("year")
    if isinstance(year, int):
        return year
    release = item.release_date or ""
    return int(release[:4]) if release[:4].isdecimal() else None


def routes(Session, Content):
    router = APIRouter(prefix="/api/v1/contents", tags=["notas IMDb"])

    @router.get("/{content_id}/imdb")
    def imdb_rating(content_id: str):
        enabled("imdb_ratings")
        with Session() as db:
            item = db.get(Content, content_id)
            if not item or item.domain not in product().domains:
                raise HTTPException(404, "Conteúdo não encontrado")
            if item.domain not in KINDS:
                raise HTTPException(404, "Notas do IMDb indisponíveis para o domínio")
        omdb = configured_provider("omdb")
        if not omdb:
            return {"configured": False, "found": False}
        imdb_id = None
        tmdb = configured_provider("tmdb")
        if item.external_provider == "omdb" and item.external_id:
            imdb_id = item.external_id
        elif item.external_provider == "tmdb" and item.external_id and tmdb:
            try:
                imdb_id = tmdb.imdb_id(item.external_id, item.domain)
            except ProviderError:
                imdb_id = None  # segue com a busca por título
        try:
            result = omdb.ratings(
                item.domain,
                imdb_id=imdb_id,
                title=None if imdb_id else item.title,
                year=None if imdb_id else _year(item),
            )
        except ProviderError as exc:
            if exc.status == 404:
                return {"configured": True, "found": False}
            raise HTTPException(exc.status, str(exc)) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(502, "Resposta externa inválida") from exc
        return {
            "configured": True,
            "found": True,
            "matched_by": "imdb_id" if imdb_id else "title",
            **result,
        }

    return router
