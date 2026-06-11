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

def run_migrations():
    from sqlalchemy import inspect, text
    import logging
    logger = logging.getLogger("posted.database")
    inspector = inspect(engine)
    if "registrants" in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('registrants')]
        
        # New Lodging Fields to check and add dynamically
        new_cols = {
            'lodging': 'VARCHAR',
            'gender_identity': 'VARCHAR',
            'roommate_preference': 'VARCHAR',
            'identified_roommate': 'VARCHAR',
            'room_id': 'VARCHAR',
            'is_write_in': 'BOOLEAN DEFAULT 0'
        }
        
        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE registrants ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column '{col_name}' to 'registrants' table successfully.")
                except Exception as e:
                    # Recheck if another instance added it concurrently
                    try:
                        re_inspector = inspect(engine)
                        re_columns = [col['name'] for col in re_inspector.get_columns('registrants')]
                        if col_name in re_columns:
                            logger.info(f"Column '{col_name}' was added concurrently by another instance.")
                        else:
                            logger.error(f"Failed to add column '{col_name}': {e}")
                    except Exception as inner_e:
                        logger.error(f"Failed to check column existence after migration failure: {inner_e}")
                        
    if "rooms" in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('rooms')]
        new_room_cols = {
            'held_by': 'VARCHAR',
            'comments': 'VARCHAR',
            'category': 'VARCHAR',
            'sort_order': 'INTEGER DEFAULT 0'
        }
        for col_name, col_type in new_room_cols.items():
            if col_name not in columns:
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE rooms ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column '{col_name}' to 'rooms' table successfully.")
                except Exception as e:
                    try:
                        re_inspector = inspect(engine)
                        re_columns = [col['name'] for col in re_inspector.get_columns('rooms')]
                        if col_name in re_columns:
                            logger.info(f"Column '{col_name}' was added concurrently to 'rooms' by another instance.")
                        else:
                            logger.error(f"Failed to add column '{col_name}' to 'rooms': {e}")
                    except Exception as inner_e:
                        logger.error(f"Failed to check rooms column existence after migration failure: {inner_e}")
