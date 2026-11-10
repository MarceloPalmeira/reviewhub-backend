import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from reviewhub_core.plugins import FeatureRegistry
from services.common import (
    configure_app,
    current_user,
    database,
    database_health,
    enabled,
    new_id,
    now,
    product,
    secret,
)
from services.migrations import migrate


class Base(DeclarativeBase):
    pass


engine, Session = database("reviews")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("author_id", "content_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    author_id: Mapped[str] = mapped_column(String, index=True)
    content_id: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String)
    rating: Mapped[float] = mapped_column(Float)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(String(10000))
    spoiler: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("review_id", "user_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    review_id: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[str] = mapped_column(String)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    review_id: Mapped[str] = mapped_column(String, index=True)
    author_id: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewInput(BaseModel):
    content_id: str
    rating: float
    title: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    spoiler: bool = False


class ReviewEdit(BaseModel):
    rating: float
    title: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    spoiler: bool = False


class CommentInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def render(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "author_id",
            "content_id",
            "domain",
            "rating",
            "title",
            "text",
            "spoiler",
            "created_at",
            "updated_at",
        )
    }


def validate(domain, data):
    try:
        FeatureRegistry(product().domains).get(domain).review_policy(
            "domain_specific_rating" in product().features
        ).validate(data.rating, data.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if data.spoiler and "spoiler_control" not in product().features:
        raise HTTPException(422, "Spoilers indisponíveis neste produto")


def catalog_item(content_id):
    try:
        response = httpx.get(
            f"{os.getenv('CATALOG_URL', 'http://localhost:8002')}/api/v1/contents/{content_id}",
            timeout=3,
        )
        if response.status_code == 404:
            raise HTTPException(404, "Conteúdo não encontrado")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Catálogo indisponível")


@asynccontextmanager
async def lifespan(app):
    product()
    secret()
    migrate("reviews", engine)
    yield


app = FastAPI(title="ReviewHub Reviews", lifespan=lifespan)
configure_app(app)


@app.get("/health")
def health():
    return database_health(engine)


@app.get("/api/v1/reviews")
def reviews(
    content_id: str | None = None,
    author_id: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    with Session() as db:
        stmt = select(Review).where(Review.domain.in_(product().domains))
        if content_id:
            stmt = stmt.where(Review.content_id == content_id)
        if author_id:
            stmt = stmt.where(Review.author_id == author_id)
        rows = db.scalars(
            stmt.order_by(Review.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return [render(row) for row in rows]


@app.post("/api/v1/reviews", status_code=201)
def create_review(data: ReviewInput, user_id: str = Depends(current_user)):
    content = catalog_item(data.content_id)
    validate(content["domain"], data)
    with Session() as db:
        row = Review(author_id=user_id, domain=content["domain"], **data.model_dump())
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            raise HTTPException(409, "Você já avaliou este conteúdo")
        return render(row)


@app.get("/api/v1/feed")
def feed(
    user_id: str = Depends(current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    enabled("social_feed")
    try:
        response = httpx.get(
            f"{os.getenv('IDENTITY_URL', 'http://localhost:8001')}/api/v1/users/{user_id}/following",
            timeout=3,
        )
        response.raise_for_status()
        followed = response.json()
        if not isinstance(followed, list) or any(
            not isinstance(item, str) for item in followed
        ):
            raise ValueError("Resposta inválida")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Identidade indisponível")
    with Session() as db:
        rows = db.scalars(
            select(Review)
            .where(Review.author_id.in_(followed), Review.domain.in_(product().domains))
            .order_by(Review.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return [render(row) for row in rows]


@app.get("/api/v1/reviews/stats")
def stats(content_id: str):
    with Session() as db:
        count, average = db.execute(
            select(func.count(Review.id), func.avg(Review.rating)).where(
                Review.content_id == content_id, Review.domain.in_(product().domains)
            )
        ).one()
        return {"count": count, "average": average}


@app.get("/api/v1/reviews/stats/batch")
def batch_stats(content_id: Annotated[list[str], Query(min_length=1, max_length=50)]):
    if any(len(value) > 100 for value in content_id):
        raise HTTPException(422, "Identificador inválido")
    with Session() as db:
        rows = db.execute(
            select(Review.content_id, func.count(Review.id), func.avg(Review.rating))
            .where(
                Review.content_id.in_(content_id), Review.domain.in_(product().domains)
            )
            .group_by(Review.content_id)
        )
        result = {value: {"count": 0, "average": None} for value in content_id}
        for value, count, average in rows:
            result[value] = {"count": count, "average": average}
        return result


@app.get("/api/v1/reviews/{review_id}")
def get_review(review_id: str):
    with Session() as db:
        row = db.get(Review, review_id)
        if not row or row.domain not in product().domains:
            raise HTTPException(404, "Review não encontrada")
        return render(row)


@app.patch("/api/v1/reviews/{review_id}")
def edit_review(review_id: str, data: ReviewEdit, user_id: str = Depends(current_user)):
    with Session() as db:
        row = db.get(Review, review_id)
        if not row or row.domain not in product().domains:
            raise HTTPException(404, "Review não encontrada")
        if row.author_id != user_id:
            raise HTTPException(403, "Você não é o autor")
        validate(row.domain, data)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        db.commit()
        return render(row)


@app.delete("/api/v1/reviews/{review_id}", status_code=204)
def delete_review(review_id: str, user_id: str = Depends(current_user)):
    with Session() as db:
        row = db.get(Review, review_id)
        if not row or row.domain not in product().domains:
            raise HTTPException(404, "Review não encontrada")
        if row.author_id != user_id:
            raise HTTPException(403, "Você não é o autor")
        for model in (Like, Comment):
            for child in db.scalars(select(model).where(model.review_id == review_id)):
                db.delete(child)
        db.delete(row)
        db.commit()


@app.get("/api/v1/reviews/{review_id}/likes")
def like_state(review_id: str, user_id: str = Depends(current_user)):
    enabled("review_likes")
    get_review(review_id)
    with Session() as db:
        count = db.scalar(
            select(func.count()).select_from(Like).where(Like.review_id == review_id)
        )
        liked = (
            db.scalar(
                select(Like.id).where(
                    Like.review_id == review_id, Like.user_id == user_id
                )
            )
            is not None
        )
        return {"count": count, "liked": liked}


@app.post("/api/v1/reviews/{review_id}/likes", status_code=204)
def like(review_id: str, user_id: str = Depends(current_user)):
    enabled("review_likes")
    get_review(review_id)
    with Session() as db:
        if not db.scalar(
            select(Like).where(Like.review_id == review_id, Like.user_id == user_id)
        ):
            db.add(Like(review_id=review_id, user_id=user_id))
            db.commit()


@app.delete("/api/v1/reviews/{review_id}/likes", status_code=204)
def unlike(review_id: str, user_id: str = Depends(current_user)):
    enabled("review_likes")
    get_review(review_id)
    with Session() as db:
        row = db.scalar(
            select(Like).where(Like.review_id == review_id, Like.user_id == user_id)
        )
        if row:
            db.delete(row)
            db.commit()


@app.get("/api/v1/reviews/{review_id}/comments")
def comments(review_id: str):
    enabled("comments")
    get_review(review_id)
    with Session() as db:
        return [
            {
                "id": c.id,
                "author_id": c.author_id,
                "text": c.text,
                "created_at": c.created_at,
            }
            for c in db.scalars(
                select(Comment)
                .where(Comment.review_id == review_id)
                .order_by(Comment.created_at)
            )
        ]


@app.post("/api/v1/reviews/{review_id}/comments", status_code=201)
def comment(review_id: str, data: CommentInput, user_id: str = Depends(current_user)):
    enabled("comments")
    get_review(review_id)
    if not data.text.strip():
        raise HTTPException(422, "Comentário vazio")
    with Session() as db:
        row = Comment(review_id=review_id, author_id=user_id, text=data.text)
        db.add(row)
        db.commit()
        return {
            "id": row.id,
            "author_id": row.author_id,
            "text": row.text,
            "created_at": row.created_at,
        }
