from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.providers.base import ProviderError
from services.catalog.providers.registry import configured_provider, provider_name
from services.common import current_user, product


class ImportInput(BaseModel):
    domain: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=100)


def routes(Session, Content, render):
    router = APIRouter(prefix="/api/v1/external", tags=["catálogo externo"])

    def select_provider(domain):
        try:
            name = provider_name(domain, product())
            return name, configured_provider(name)
        except ProviderError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @router.get("/search")
    def search(
        domain: str,
        q: str = Query(min_length=2, max_length=100),
        page: int = Query(1, ge=1, le=100),
    ):
        if len(q.strip()) < 2:
            raise HTTPException(422, "Informe ao menos dois caracteres")
        name, provider = select_provider(domain)
        if not provider:
            return {"provider": name, "configured": False, "results": []}
        try:
            return {
                "provider": name,
                "configured": True,
                "results": provider.search(q.strip(), domain, page),
            }
        except ProviderError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(502, "Resposta externa inválida") from exc

    @router.get("/{domain}/{external_id}")
    def details(domain: str, external_id: str):
        _, provider = select_provider(domain)
        if not provider:
            raise HTTPException(503, "Provedor não configurado")
        try:
            return provider.get_details(external_id, domain)
        except ProviderError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(502, "Resposta externa inválida") from exc

    @router.post("/import", status_code=200)
    def import_content(data: ImportInput, user_id: str = Depends(current_user)):
        name, provider = select_provider(data.domain)
        with Session() as db:
            query = select(Content).where(
                Content.external_provider == name,
                Content.domain == data.domain,
                Content.external_id == data.external_id,
            )
            existing = db.scalar(query)
            if existing:
                return render(existing)
            if not provider:
                raise HTTPException(503, "Provedor não configurado")
            try:
                external = provider.get_details(data.external_id, data.domain)
                if (
                    external.provider != name
                    or external.domain != data.domain
                    or external.external_id != data.external_id
                ):
                    raise ProviderError("Resposta externa incompatível", 502)
                plugin = FeatureRegistry(product().domains).get(data.domain)
                metadata = plugin.visible_metadata(
                    external.metadata, product().features
                )
                metadata = plugin.schema.model_validate(metadata).model_dump(
                    exclude_none=True, mode="json"
                )
            except ProviderError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
            except (ValidationError, ValueError, TypeError, KeyError) as exc:
                raise HTTPException(
                    422, "Dados externos incompletos ou inválidos"
                ) from exc
            item = Content(
                domain=data.domain,
                title=external.title,
                description=external.description,
                metadata_json=metadata,
                cover_url=external.cover_url,
                backdrop_url=external.backdrop_url,
                release_date=external.release_date,
                genres=external.genres,
                external_provider=name,
                external_id=data.external_id,
            )
            db.add(item)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.scalar(query)
                if existing:
                    return render(existing)
                raise
            return render(item)

    return router
