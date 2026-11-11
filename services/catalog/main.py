from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common import (
    configure_app,
    current_user,
    database,
    database_health,
    enabled,
    new_id,
    now,
    product,
    registry,
    secret,
)
from services.migrations import migrate


class Base(DeclarativeBase):
    pass


engine, Session = database("catalog")


class Content(Base):
    __tablename__ = "contents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    domain: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(String(4000))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    external_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    backdrop_url: Mapped[str | None] = mapped_column(String, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    genres: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class CustomList(Base):
    __tablename__ = "custom_lists"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ListItem(Base):
    __tablename__ = "list_items"
    __table_args__ = (UniqueConstraint("list_id", "content_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    list_id: Mapped[str] = mapped_column(
        ForeignKey("custom_lists.id", ondelete="CASCADE"), index=True
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE")
    )


class ListInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)


class ListItemInput(BaseModel):
    content_id: str = Field(min_length=1, max_length=100)


class ContentCreate(BaseModel):
    domain: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=4000)
    metadata: dict
    cover_url: str | None = None


def render(item):
    return {
        "id": item.id,
        "domain": item.domain,
        "title": item.title,
        "description": item.description,
        "metadata": registry()
        .get(item.domain)
        .visible_metadata(item.metadata_json, product().features),
        "cover_url": item.cover_url,
        "backdrop_url": item.backdrop_url,
        "release_date": item.release_date,
        "genres": item.genres or [],
        "external_provider": item.external_provider,
        "external_id": item.external_id,
        "created_at": item.created_at,
    }


@asynccontextmanager
async def lifespan(app):
    product()
    secret()
    migrate("catalog", engine)
    yield


app = FastAPI(title="ReviewHub Catalog", lifespan=lifespan)
configure_app(app)


@app.get("/health")
def health():
    return database_health(engine)


@app.get("/api/v1/domains")
def domains():
    return product().domains


@app.get("/api/v1/contents")
def contents(
    q: str = "",
    domain: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    content_id: Annotated[list[str] | None, Query(max_length=100)] = None,
):
    """Lista paginada; `content_id` repetido busca vários conteúdos em lote."""
    available = product().domains
    if domain and domain not in available:
        raise HTTPException(404, "Domínio indisponível")
    with Session() as db:
        stmt = select(Content).where(
            Content.domain.in_([domain] if domain else available),
            Content.title.ilike(f"%{q}%"),
        )
        if content_id:
            stmt = stmt.where(Content.id.in_(content_id))
        stmt = (
            stmt.order_by(Content.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return [render(item) for item in db.scalars(stmt)]


@app.get("/api/v1/contents/{content_id}")
def get_content(content_id: str):
    with Session() as db:
        item = db.get(Content, content_id)
        if not item or item.domain not in product().domains:
            raise HTTPException(404, "Conteúdo não encontrado")
        return render(item)


@app.post("/api/v1/contents", status_code=201)
def create_content(data: ContentCreate, user_id: str = Depends(current_user)):
    try:
        metadata = (
            registry()
            .get(data.domain)
            .validate_metadata(data.metadata, product().features)
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc))
    with Session() as db:
        item = Content(
            domain=data.domain,
            title=data.title,
            description=data.description,
            metadata_json=metadata,
            cover_url=data.cover_url,
        )
        db.add(item)
        db.commit()
        return render(item)


def owned_list(db, list_id: str, user_id: str):
    row = db.get(CustomList, list_id)
    if row is None:
        raise HTTPException(404, "Lista não encontrada")
    if row.owner_id != user_id:
        raise HTTPException(403, "A lista pertence a outro usuário")
    return row


def render_list(db, row):
    contents = db.scalars(
        select(Content)
        .join(ListItem, ListItem.content_id == Content.id)
        .where(ListItem.list_id == row.id, Content.domain.in_(product().domains))
        .order_by(Content.title)
    )
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at,
        "items": [render(item) for item in contents],
    }


@app.get("/api/v1/lists")
def lists(user_id: str = Depends(current_user)):
    enabled("custom_lists")
    with Session() as db:
        return [
            render_list(db, row)
            for row in db.scalars(
                select(CustomList)
                .where(CustomList.owner_id == user_id)
                .order_by(CustomList.created_at.desc())
            )
        ]


@app.post("/api/v1/lists", status_code=201)
def create_list(data: ListInput, user_id: str = Depends(current_user)):
    enabled("custom_lists")
    if not data.name.strip():
        raise HTTPException(422, "Nome da lista não pode ficar vazio")
    with Session() as db:
        row = CustomList(
            owner_id=user_id, name=data.name.strip(), description=data.description
        )
        db.add(row)
        db.commit()
        return render_list(db, row)


@app.get("/api/v1/lists/{list_id}")
def get_list(list_id: str, user_id: str = Depends(current_user)):
    enabled("custom_lists")
    with Session() as db:
        return render_list(db, owned_list(db, list_id, user_id))


@app.patch("/api/v1/lists/{list_id}")
def edit_list(list_id: str, data: ListInput, user_id: str = Depends(current_user)):
    enabled("custom_lists")
    if not data.name.strip():
        raise HTTPException(422, "Nome da lista não pode ficar vazio")
    with Session() as db:
        row = owned_list(db, list_id, user_id)
        row.name, row.description = data.name.strip(), data.description
        db.commit()
        return render_list(db, row)


@app.delete("/api/v1/lists/{list_id}", status_code=204)
def delete_list(list_id: str, user_id: str = Depends(current_user)):
    enabled("custom_lists")
    with Session() as db:
        row = owned_list(db, list_id, user_id)
        for item in db.scalars(select(ListItem).where(ListItem.list_id == row.id)):
            db.delete(item)
        db.delete(row)
        db.commit()


@app.post("/api/v1/lists/{list_id}/items", status_code=201)
def add_list_item(
    list_id: str, data: ListItemInput, user_id: str = Depends(current_user)
):
    enabled("custom_lists")
    with Session() as db:
        row = owned_list(db, list_id, user_id)
        content = db.get(Content, data.content_id)
        if not content or content.domain not in product().domains:
            raise HTTPException(404, "Conteúdo não encontrado")
        db.add(ListItem(list_id=list_id, content_id=data.content_id))
        try:
            db.commit()
        except IntegrityError:
            raise HTTPException(409, "Conteúdo já está na lista")
        return render_list(db, row)


@app.delete("/api/v1/lists/{list_id}/items/{content_id}", status_code=204)
def remove_list_item(
    list_id: str, content_id: str, user_id: str = Depends(current_user)
):
    enabled("custom_lists")
    with Session() as db:
        owned_list(db, list_id, user_id)
        item = db.scalar(
            select(ListItem).where(
                ListItem.list_id == list_id, ListItem.content_id == content_id
            )
        )
        if item is None:
            raise HTTPException(404, "Item não encontrado")
        db.delete(item)
        db.commit()


from services.catalog.external_routes import routes as external_routes
from services.catalog.imdb_routes import routes as imdb_routes

app.include_router(external_routes(Session, Content, render))
app.include_router(imdb_routes(Session, Content))
