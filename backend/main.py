from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import List, Optional
import os
import uuid
import logging
import datetime

from backend.config import settings
from backend.database import get_db, engine, Base
from backend.models import Presenter
from backend.schemas import DrupalWebhookPayload, PresenterResponse
from backend.download_assets import download_assets

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("posted.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Create tables dynamically
    logger.info("Initializing database and tables...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")

    # 2. Startup: Sync static assets from main site
    logger.info("Syncing branding assets and stylesheets from caarms.princeton.edu...")
    try:
        download_assets(force=False)
        logger.info("Static assets verified.")
    except Exception as e:
        logger.error(f"Failed to sync static assets on startup: {e}")

    yield
    # Shutdown steps (none needed)

app = FastAPI(title="Poster Presenters Portal", lifespan=lifespan)

# Mount static files folder
os.makedirs("frontend/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# --- Root HTML Routers ---

@app.get("/")
async def get_root():
    with open("frontend/index.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.get("/index.html")
async def get_index_html():
    with open("frontend/index.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


# --- API Endpoints ---

# 1. Public endpoint to list all poster presenters
@app.get("/api/presenters", response_model=List[PresenterResponse])
async def list_presenters(db: Session = Depends(get_db)):
    # Returns all visible presenters, ordered alphabetically by last name
    presenters = db.query(Presenter)\
        .filter(Presenter.is_visible == True)\
        .order_by(Presenter.last_name.asc(), Presenter.first_name.asc())\
        .all()
    return presenters


# 2. Secure Drupal Webhook Remote Post Endpoint
@app.post("/api/drupal-webhook")
async def drupal_webhook(
    payload: DrupalWebhookPayload,
    x_drupal_webhook_token: Optional[str] = Header(None, alias="X-Drupal-Webhook-Token"),
    db: Session = Depends(get_db)
):
    # Validate Webhook Secret Header
    if not x_drupal_webhook_token or x_drupal_webhook_token != settings.drupal_webhook_token:
        logger.error("Drupal webhook authentication failed: missing or invalid token header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook authentication token."
        )

    if not payload.email_address:
        logger.error("Webhook payload rejected: email_address is missing.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email_address field is required."
        )

    # Check if they are presenting a poster
    is_presenting = False
    if payload.presenting_poster:
        val = payload.presenting_poster.strip().lower()
        is_presenting = val in ("1", "true", "yes", "on", "checked")

    # Locate existing entry by email (case-insensitive due to lowcasing in schema validation)
    existing_presenter = db.query(Presenter).filter(Presenter.email_address == payload.email_address).first()

    if not is_presenting:
        # If they are NOT presenting, but have an existing record, we mark it invisible
        if existing_presenter:
            logger.info(f"Presenter {payload.email_address} marked as invisible (toggle set to No).")
            existing_presenter.is_visible = False
            db.commit()
            return {"status": "success", "message": "Presenter marked as inactive.", "email": payload.email_address}
        return {"status": "ignored", "message": "Submission ignored (presenting_poster is not Yes)."}

    # Validate that we have poster details (title, adviser, abstract)
    if not payload.poster_title or not payload.faculty_adviser_name or not payload.poster_presentation_abstract:
        logger.warning(f"Submission for {payload.email_address} specifies presenting, but is missing details.")

    # Upsert Logic: Update if exists, otherwise create
    if existing_presenter:
        logger.info(f"Updating existing poster presenter: {payload.email_address}")
        existing_presenter.first_name = payload.first_name or existing_presenter.first_name
        existing_presenter.last_name = payload.last_name or existing_presenter.last_name
        existing_presenter.poster_title = payload.poster_title or existing_presenter.poster_title
        existing_presenter.faculty_adviser_name = payload.faculty_adviser_name or existing_presenter.faculty_adviser_name
        existing_presenter.poster_presentation_abstract = payload.poster_presentation_abstract or existing_presenter.poster_presentation_abstract
        existing_presenter.drupal_sid = payload.sid or existing_presenter.drupal_sid
        existing_presenter.serial_number = payload.serial or existing_presenter.serial_number
        existing_presenter.is_visible = True
        existing_presenter.registered_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(existing_presenter)
        return {"status": "success", "message": "Presenter updated successfully.", "id": existing_presenter.id}
    else:
        logger.info(f"Creating new poster presenter: {payload.email_address}")
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
        db.commit()
        db.refresh(new_presenter)
        return {"status": "success", "message": "Presenter registered successfully.", "id": new_presenter.id}
