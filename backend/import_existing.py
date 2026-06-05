import sys
import os
import json
import uuid
import datetime

# Add project root to python path to allow absolute imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, Base, engine
from backend.models import Presenter
from backend.schemas import DrupalWebhookPayload

def import_submissions(file_path: str):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading or parsing JSON file: {e}")
        sys.exit(1)

    # Normalize data: handles list format or dictionary-of-submissions format
    records = []
    if isinstance(data, dict):
        # Check if the keys represent submission IDs
        first_key = next(iter(data.keys())) if data else None
        if first_key and (first_key.isdigit() or len(first_key) > 30):
            records = list(data.values())
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        print("Error: Unsupported JSON root format (must be list or dict of submissions).")
        sys.exit(1)

    print(f"Found {len(records)} submissions in file. Commencing import...")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    imported_count = 0
    updated_count = 0
    ignored_count = 0

    try:
        for idx, rec in enumerate(records):
            try:
                # Use Pydantic schema to parse the record exactly like the webhook does
                payload = DrupalWebhookPayload.model_validate(rec)
            except Exception as e:
                print(f"Warning: Failed to validate submission at index {idx}: {e}")
                ignored_count += 1
                continue

            if not payload.email_address:
                ignored_count += 1
                continue

            # Verify if the toggle presenting_poster is set to Yes
            is_presenting = False
            if payload.presenting_poster:
                is_presenting = payload.presenting_poster.strip().lower() in ("1", "true", "yes", "on", "checked")

            if not is_presenting:
                ignored_count += 1
                continue

            # Query existing presenter by email to prevent duplicate conflicts
            existing_presenter = db.query(Presenter).filter(Presenter.email_address == payload.email_address).first()

            if existing_presenter:
                existing_presenter.first_name = payload.first_name or existing_presenter.first_name
                existing_presenter.last_name = payload.last_name or existing_presenter.last_name
                existing_presenter.poster_title = payload.poster_title or existing_presenter.poster_title
                existing_presenter.faculty_adviser_name = payload.faculty_adviser_name or existing_presenter.faculty_adviser_name
                existing_presenter.poster_presentation_abstract = payload.poster_presentation_abstract or existing_presenter.poster_presentation_abstract
                existing_presenter.drupal_sid = payload.sid or existing_presenter.drupal_sid
                existing_presenter.serial_number = payload.serial or existing_presenter.serial_number
                existing_presenter.is_visible = True
                existing_presenter.registered_at = datetime.datetime.utcnow()
                updated_count += 1
            else:
                new_presenter = Presenter(
                    id=str(uuid.uuid4()),
                    email_address=payload.email_address,
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    poster_title=payload.poster_title,
                    faculty_adviser_name=payload.faculty_adviser_name,
                    poster_presentation_abstract=payload.poster_presentation_abstract,
                    drupal_sid=payload.sid,
                    serial_number=payload.serial,
                    is_visible=True,
                    registered_at=datetime.datetime.utcnow()
                )
                db.add(new_presenter)
                imported_count += 1

        db.commit()
        print("\n--- Import Summary ---")
        print(f"Successfully Imported (New): {imported_count}")
        print(f"Successfully Updated (Existing): {updated_count}")
        print(f"Ignored/Skipped (Non-poster/Invalid): {ignored_count}")
        print("----------------------")

    except Exception as e:
        db.rollback()
        print(f"Error during database operations: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/import_existing.py <path_to_drupal_export.json>")
        sys.exit(1)
        
    import_submissions(sys.argv[1])
