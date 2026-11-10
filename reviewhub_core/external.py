"""Contratos de provedores externos independentes de FastAPI e de domínios."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ExternalContent(BaseModel):
    provider: str
    external_id: str
    domain: str
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    cover_url: str | None = None
    backdrop_url: str | None = None
    release_date: str | None = None
    genres: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ExternalCatalogProvider(ABC):
    @abstractmethod
    def search(
        self, query: str, domain: str, page: int = 1
    ) -> list[ExternalContent]: ...

    @abstractmethod
    def get_details(self, external_id: str, domain: str) -> ExternalContent: ...

    @abstractmethod
    def normalize_content(self, data: dict, domain: str) -> ExternalContent: ...

    def get_images(self, content: ExternalContent) -> dict:
        return {"cover_url": content.cover_url, "backdrop_url": content.backdrop_url}
