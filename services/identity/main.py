from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common import (
    configure_app,
    current_user,
    database,
    database_health,
    enabled,
    new_id,
    product,
    secret,
    token_for,
)
from services.migrations import migrate


class Base(DeclarativeBase):
    pass


engine, Session = database("identity")
passwords = PasswordHash.recommended()


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    bio: Mapped[str] = mapped_column(String(500), default="")


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followed_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    follower_id: Mapped[str] = mapped_column(String, index=True)
    followed_id: Mapped[str] = mapped_column(String, index=True)


class Register(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    password: str = Field(min_length=8, max_length=128)


class Login(BaseModel):
    username: str
    password: str


class ProfileEdit(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=500)


def public(user):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "bio": user.bio,
    }


@asynccontextmanager
async def lifespan(app):
    product()
    secret()
    migrate("identity", engine)
    yield


app = FastAPI(title="ReviewHub Identity", lifespan=lifespan)
configure_app(app)


@app.get("/health")
def health():
    return database_health(engine)


@app.post("/api/v1/auth/register", status_code=201)
def register(data: Register):
    with Session() as db:
        if db.scalar(
            select(User).where(
                (User.username == data.username) | (User.email == data.email.lower())
            )
        ):
            raise HTTPException(409, "Usuário ou e-mail já cadastrado")
        user = User(
            username=data.username,
            display_name=data.display_name,
            email=data.email.lower(),
            password_hash=passwords.hash(data.password),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            raise HTTPException(409, "Usuário ou e-mail já cadastrado")
        return public(user)


@app.post("/api/v1/auth/login")
def login(data: Login):
    with Session() as db:
        user = db.scalar(select(User).where(User.username == data.username))
        if not user or not passwords.verify(data.password, user.password_hash):
            raise HTTPException(401, "Credenciais inválidas")
        return {
            "access_token": token_for(user.id),
            "token_type": "bearer",
            "user": public(user),
        }


@app.get("/api/v1/users/me")
def me(user_id: str = Depends(current_user)):
    return get_user(user_id)


@app.patch("/api/v1/users/me")
def edit_me(data: ProfileEdit, user_id: str = Depends(current_user)):
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        for key, value in data.model_dump(
            exclude_unset=True, exclude_none=True
        ).items():
            setattr(user, key, value)
        db.commit()
        return public(user)


@app.get("/api/v1/users/{user_id}")
def get_user(user_id: str):
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(404, "Usuário não encontrado")
        return public(user)


@app.get("/api/v1/users/{user_id}/following")
def following(user_id: str):
    enabled("user_follows")
    with Session() as db:
        return list(
            db.scalars(select(Follow.followed_id).where(Follow.follower_id == user_id))
        )


@app.post("/api/v1/users/{target}/follow", status_code=204)
def follow(target: str, user_id: str = Depends(current_user)):
    enabled("user_follows")
    if target == user_id:
        raise HTTPException(400, "Você não pode seguir a si mesmo")
    with Session() as db:
        if not db.get(User, target):
            raise HTTPException(404, "Usuário não encontrado")
        if not db.scalar(
            select(Follow).where(
                Follow.follower_id == user_id, Follow.followed_id == target
            )
        ):
            db.add(Follow(follower_id=user_id, followed_id=target))
            db.commit()


@app.delete("/api/v1/users/{target}/follow", status_code=204)
def unfollow(target: str, user_id: str = Depends(current_user)):
    enabled("user_follows")
    with Session() as db:
        row = db.scalar(
            select(Follow).where(
                Follow.follower_id == user_id, Follow.followed_id == target
            )
        )
        if row:
            db.delete(row)
            db.commit()


@app.get("/api/v1/users/{user_id}/social")
def social_stats(user_id: str):
    enabled("user_follows")
    with Session() as db:
        if not db.get(User, user_id):
            raise HTTPException(404, "Usuário não encontrado")
        followers = db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.followed_id == user_id)
        )
        following = db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.follower_id == user_id)
        )
        return {"followers": followers, "following": following}
