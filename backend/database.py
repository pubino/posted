from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging
from backend.config import settings

DATABASE_URL = settings.database_url
logger = logging.getLogger("posted.database")

# Ensure the database directory exists if using SQLite
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL
    if db_path.startswith("sqlite:////"):
        db_path = db_path.replace("sqlite:////", "/")
    elif db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created SQLite database directory: {db_dir}")
        except Exception as e:
            logger.warning(f"Could not create SQLite database directory {db_dir}: {e}")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
