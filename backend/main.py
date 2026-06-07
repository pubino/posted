from fastapi import FastAPI, Depends, Header, HTTPException, status, Request, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import List, Optional
import os
import uuid
import logging
import datetime
import shutil

from backend.config import settings
from backend.database import get_db, engine, Base, run_migrations
from backend.models import Presenter, Registrant, Room
from backend.schemas import DrupalWebhookPayload, PresenterResponse, NametagsWebhookPayload, RegistrantResponse, RoomResponse, RoomCreate, RoomAssignmentPayload, RoomUpdate
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
        run_migrations()
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


# --- RSS Feed Routers ---

@app.get("/feed.xml")
@app.get("/rss.xml")
async def get_rss_feed(request: Request, db: Session = Depends(get_db)):
    import email.utils
    import xml.etree.ElementTree as ET
    from datetime import timezone

    # Query all visible presenters, ordered alphabetically by last name
    presenters = db.query(Presenter)\
        .filter(Presenter.is_visible == True)\
        .order_by(Presenter.last_name.asc(), Presenter.first_name.asc())\
        .all()

    base_url = str(request.base_url).rstrip("/")
    now = datetime.datetime.now(timezone.utc)

    # Construct RSS 2.0 XML
    rss = ET.Element("rss", version="2.0", **{"xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "CAARMS 2026 Poster Presenters"
    ET.SubElement(channel, "link").text = f"{base_url}/"
    ET.SubElement(channel, "description").text = "List of registered poster presentations for CAARMS 2026."
    
    # Self reference link
    ET.SubElement(channel, "atom:link", href=f"{base_url}/feed.xml", rel="self", type="application/rss+xml")
    
    # Last Build Date (RFC 822 format)
    ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(now)

    for p in presenters:
        item = ET.SubElement(channel, "item")
        
        # Title of item
        title_str = p.poster_title or "Untitled Presentation"
        ET.SubElement(item, "title").text = title_str
        
        # Link back to specific presenter details on page
        ET.SubElement(item, "link").text = f"{base_url}/?presenter={p.id}"
        ET.SubElement(item, "guid", isPermaLink="false").text = p.id
        
        # PubDate
        pub_dt = p.registered_at.replace(tzinfo=timezone.utc) if p.registered_at else now
        ET.SubElement(item, "pubDate").text = email.utils.format_datetime(pub_dt)
        
        # Description containing presenter name and faculty adviser with forced line break
        name_str = f"{p.first_name} {p.last_name}" if (p.first_name or p.last_name) else "Unknown Presenter"
        adviser = p.faculty_adviser_name or "N/A"
        desc_content = f"<strong>Presenter:</strong> {name_str}<br/>\n<strong>Faculty Adviser:</strong> {adviser}"
        ET.SubElement(item, "description").text = desc_content

    xml_data = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return Response(content=xml_data, media_type="application/rss+xml")


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


# --- Nametags & Admin Generator Extension ---

def is_admin_authorized(request: Request) -> bool:
    # 1. Fetch principal name from Azure Easy Auth header
    principal_name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME")
    
    # 2. Local development fallback
    if not principal_name and os.getenv("ALLOW_LOCAL_DEV_ADMIN") == "true":
        principal_name = request.headers.get("X-Mock-Admin-Principal", "bino@princeton.edu")
        
    if not principal_name or principal_name.strip().lower() == "anonymous":
        return False
        
    # 3. Verify against allowed principals
    allowed = [email.strip().lower() for email in settings.allowed_admin_principals.split(",")]
    return principal_name.strip().lower() in allowed


@app.post("/api/nametags-webhook")
@app.post("/api/nametags-lodging-webhook")
async def nametags_webhook(
    payload: NametagsWebhookPayload,
    x_drupal_webhook_token: Optional[str] = Header(None, alias="X-Drupal-Webhook-Token"),
    db: Session = Depends(get_db)
):
    if not x_drupal_webhook_token or x_drupal_webhook_token != settings.nametags_webhook_token:
        logger.error("Nametags webhook auth failed: invalid token header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook authentication token."
        )

    if not payload.email_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email_address is required."
        )

    existing = db.query(Registrant).filter(Registrant.email_address == payload.email_address).first()
    
    if existing:
        logger.info(f"Updating registrant: {payload.email_address}")
        existing.first_name = payload.first_name or existing.first_name
        existing.last_name = payload.last_name or existing.last_name
        existing.home_institution_or_organization = payload.home_institution_or_organization or existing.home_institution_or_organization
        existing.attendee_status = payload.attendee_status or existing.attendee_status
        existing.student = payload.student or existing.student
        existing.t_shirt_size = payload.t_shirt_size or existing.t_shirt_size
        existing.presenting_poster = payload.presenting_poster or existing.presenting_poster
        existing.lodging = payload.lodging or existing.lodging
        existing.gender_identity = payload.gender_identity or existing.gender_identity
        existing.roommate_preference = payload.roommate_preference or existing.roommate_preference
        existing.identified_roommate = payload.identified_roommate or existing.identified_roommate
        existing.drupal_sid = payload.sid or existing.drupal_sid
        existing.serial_number = payload.serial or existing.serial_number
        existing.registered_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return {"status": "success", "message": "Registrant updated.", "id": existing.id}
    else:
        logger.info(f"Creating registrant: {payload.email_address}")
        new_reg = Registrant(
            id=str(uuid.uuid4()),
            email_address=payload.email_address,
            first_name=payload.first_name,
            last_name=payload.last_name,
            home_institution_or_organization=payload.home_institution_or_organization,
            attendee_status=payload.attendee_status,
            student=payload.student,
            t_shirt_size=payload.t_shirt_size,
            presenting_poster=payload.presenting_poster,
            lodging=payload.lodging,
            gender_identity=payload.gender_identity,
            roommate_preference=payload.roommate_preference,
            identified_roommate=payload.identified_roommate,
            drupal_sid=payload.sid,
            serial_number=payload.serial,
            registered_at=datetime.datetime.utcnow()
        )
        db.add(new_reg)
        db.commit()
        db.refresh(new_reg)
        return {"status": "success", "message": "Registrant registered successfully.", "id": new_reg.id}


@app.get("/admin/nametags")
async def get_admin_nametags(request: Request):
    if not is_admin_authorized(request):
        principal_name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME")
        if (not principal_name or principal_name.strip().lower() == "anonymous") and os.getenv("ALLOW_LOCAL_DEV_ADMIN") != "true":
            return RedirectResponse(url="/.auth/login/aad?post_login_redirect_uri=/admin/nametags")
        raise HTTPException(status_code=403, detail="Access Forbidden: Unauthorized user principal.")
    with open("frontend/admin_nametags.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


@app.get("/api/admin/registrants", response_model=List[RegistrantResponse])
async def list_admin_registrants(request: Request, db: Session = Depends(get_db)):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden: Unauthorized user principal.")
    registrants = db.query(Registrant).order_by(Registrant.last_name.asc(), Registrant.first_name.asc()).all()
    return registrants


@app.post("/api/admin/upload-logo")
async def upload_logo(
    request: Request,
    logo_type: str = Form(...),
    file: UploadFile = File(...)
):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
    
    # Determine extension
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower() if filename else ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".svg"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PNG, JPG, or SVG allowed.")
        
    os.makedirs("frontend/static/images", exist_ok=True)
    # We save custom files as badge_primary_custom{ext} or badge_sponsor_custom{ext}
    target_name = f"badge_{logo_type}_custom{ext}"
    dest_path = os.path.join("frontend", "static", "images", target_name)
    
    # Write file
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"status": "success", "url": f"/static/images/{target_name}"}


# --- Lodging & Room Assignment Admin Endpoints ---

@app.get("/admin/lodging")
async def get_admin_lodging(request: Request):
    if not is_admin_authorized(request):
        principal_name = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME")
        if (not principal_name or principal_name.strip().lower() == "anonymous") and os.getenv("ALLOW_LOCAL_DEV_ADMIN") != "true":
            return RedirectResponse(url="/.auth/login/aad?post_login_redirect_uri=/admin/lodging")
        raise HTTPException(status_code=403, detail="Access Forbidden: Unauthorized user principal.")
    with open("frontend/admin_lodging.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


@app.get("/api/admin/rooms", response_model=List[RoomResponse])
async def list_admin_rooms(request: Request, db: Session = Depends(get_db)):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
    rooms = db.query(Room).order_by(Room.name.asc()).all()
    return rooms


@app.post("/api/admin/rooms", response_model=RoomResponse)
async def create_admin_room(
    request: Request,
    payload: RoomCreate,
    db: Session = Depends(get_db)
):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
        
    # Check duplicate name
    existing_room = db.query(Room).filter(Room.name == payload.name.strip()).first()
    if existing_room:
        raise HTTPException(status_code=400, detail="A room with this name already exists.")
        
    room = Room(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        capacity=payload.capacity,
        room_gender=payload.room_gender
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@app.delete("/api/admin/rooms/{room_id}")
async def delete_admin_room(
    request: Request,
    room_id: str,
    db: Session = Depends(get_db)
):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
        
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    # Unassign all registrants from this room
    db.query(Registrant).filter(Registrant.room_id == room_id).update({Registrant.room_id: None})
    
    db.delete(room)
    db.commit()
    return {"status": "success", "message": "Room deleted and assignments cleared."}


@app.patch("/api/admin/rooms/{room_id}", response_model=RoomResponse)
async def update_admin_room(
    request: Request,
    room_id: str,
    payload: RoomUpdate,
    db: Session = Depends(get_db)
):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
        
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    # Check if we are trying to update name, capacity, or room_gender
    has_unoccupied_fields = (
        (payload.name is not None and payload.name.strip() != room.name) or
        (payload.capacity is not None and payload.capacity != room.capacity) or
        (payload.room_gender is not None and payload.room_gender != room.room_gender)
    )
    
    if has_unoccupied_fields:
        occupants_count = db.query(Registrant).filter(Registrant.room_id == room_id).count()
        if occupants_count > 0:
            raise HTTPException(
                status_code=400, 
                detail="Cannot edit Name, Capacity, or Gender Constraint of an occupied room."
            )
            
        if payload.name is not None:
            name_stripped = payload.name.strip()
            if name_stripped != room.name:
                existing_room = db.query(Room).filter(Room.name == name_stripped).first()
                if existing_room:
                    raise HTTPException(status_code=400, detail="A room with this name already exists.")
                room.name = name_stripped
                
        if payload.capacity is not None:
            if payload.capacity <= 0:
                raise HTTPException(status_code=400, detail="Capacity must be greater than zero.")
            room.capacity = payload.capacity
            
        if payload.room_gender is not None:
            room.room_gender = payload.room_gender
            
    # Always allow updating held_by and comments
    if payload.held_by is not None:
        room.held_by = payload.held_by
    if payload.comments is not None:
        room.comments = payload.comments
        
    db.commit()
    db.refresh(room)
    return room


@app.post("/api/admin/rooms/assign")
async def assign_admin_room(
    request: Request,
    payload: RoomAssignmentPayload,
    db: Session = Depends(get_db)
):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
        
    registrant = db.query(Registrant).filter(Registrant.id == payload.registrant_id).first()
    if not registrant:
        raise HTTPException(status_code=404, detail="Registrant not found")
        
    if payload.room_id:
        room = db.query(Room).filter(Room.id == payload.room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
            
        # Check capacity
        current_occupants = db.query(Registrant).filter(Registrant.room_id == payload.room_id).count()
        if current_occupants >= room.capacity:
            raise HTTPException(status_code=400, detail="Room is already at full capacity")
            
        registrant.room_id = payload.room_id
    else:
        registrant.room_id = None
        
    db.commit()
    return {"status": "success", "message": "Room assignment updated."}


@app.get("/api/admin/lodging/registrants", response_model=List[RegistrantResponse])
async def list_admin_lodging_registrants(request: Request, db: Session = Depends(get_db)):
    if not is_admin_authorized(request):
        raise HTTPException(status_code=403, detail="Access Forbidden")
    registrants = db.query(Registrant).filter(
        (Registrant.lodging == "Yes") | (Registrant.lodging == "yes")
    ).order_by(Registrant.last_name.asc(), Registrant.first_name.asc()).all()
    return registrants
