import os
from datetime import timedelta


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///urna_local.db")
    # O Neon entrega "postgresql://"; o SQLAlchemy precisa saber o driver (psycopg 3).
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = _database_url()
    # O Neon "dorme" quando ocioso: pre_ping/recycle evitam conexões mortas.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-chave-insegura-troque"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    # Só quem tem ADMIN_USER/ADMIN_PASSWORD cria contas de mesário (/admin).
    ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
