import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _build_database_uri() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url.replace("postgres://", "postgresql://", 1)
    return f"sqlite:///{BASE_DIR / 'qatar_foundation_admin.db'}"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key")
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RESET_PASSWORD_SALT = "admin-password-reset"
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
