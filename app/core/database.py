import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from functools import wraps
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Create engine and session
db_url = os.getenv("DB_URL")

engine = None
SessionLocal = None
if db_url:
    engine = create_engine(
        db_url,
        connect_args={"options": "-csearch_path=public"}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables defined in SQLAlchemy models (new tables only — existing ones are untouched)."""
    if engine is None:
        return
    from app.models import Base  # noqa: F401 — ensures all models are registered
    Base.metadata.create_all(bind=engine, checkfirst=True)


def get_db():
    if SessionLocal is None:
        raise HTTPException(
            status_code=500,
            detail="Database is not configured. Missing DB_URL environment variable."
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def handle_database_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as e:
            error_message = f"Database error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_message)

    return wrapper
