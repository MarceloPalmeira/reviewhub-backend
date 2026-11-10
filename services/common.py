import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from reviewhub_core.features import Product


def product():
    path = Path(os.getenv("PRODUCT_CONFIG", "generated/product.json"))
    return Product.model_validate(json.loads(path.read_text(encoding="utf-8")))


def enabled(feature: str):
    if feature not in product().features:
        raise HTTPException(404, "Funcionalidade indisponível neste produto")


def database(name: str):
    url = os.environ.get(f"{name.upper()}_DATABASE_URL", f"sqlite:///./{name}.db")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def new_id():
    return str(uuid4())


def now():
    return datetime.now(UTC)


def secret():
    value = os.getenv("JWT_SECRET")
    if not value or len(value) < 32:
        raise RuntimeError("JWT_SECRET deve ter pelo menos 32 caracteres")
    return value


def token_for(user_id: str):
    return jwt.encode(
        {"sub": user_id, "exp": now() + timedelta(hours=2)}, secret(), algorithm="HS256"
    )


bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    try:
        if not credentials:
            raise ValueError("Token ausente")
        payload = jwt.decode(
            credentials.credentials,
            secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        return str(payload["sub"])
    except (InvalidTokenError, ValueError):
        raise HTTPException(
            401, "Token inválido ou expirado", headers={"WWW-Authenticate": "Bearer"}
        )


def configure_app(app):
    origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


def database_health(engine):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Banco de dados indisponível")
    return {"status": "ok"}
