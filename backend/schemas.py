from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Any
import datetime

class DrupalWebhookPayload(BaseModel):
    email_address: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    presenting_poster: Optional[str] = None
    poster_title: Optional[str] = None
    faculty_adviser_name: Optional[str] = None
    poster_presentation_abstract: Optional[str] = None
    sid: Optional[int] = None
    serial: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def parse_drupal_payload(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        # Locate the data block (Drupal Remote Post wraps submissions in "data")
        data_block = values.get("data")
        if not isinstance(data_block, dict):
            data_block = values

        # Extract SID and Serial
        sid = values.get("sid") or data_block.get("sid") or data_block.get("submission_id")
        serial = values.get("serial") or data_block.get("serial") or data_block.get("serial_number")

        # Extract Presenting Poster toggle
        presenting_poster = data_block.get("presenting_poster")

        # Extract Email Address (handles strings & composite Drupal email confirmation structures)
        email_val = data_block.get("email_address") or data_block.get("email") or data_block.get("mail")
        email_address = None
        if isinstance(email_val, dict):
            email_address = email_val.get("mail_1") or email_val.get("email") or email_val.get("value")
        elif isinstance(email_val, str):
            email_address = email_val

        if email_address:
            email_address = email_address.strip().lower()

        # Extract Name (handles strings & composite Drupal name structures)
        first_name = data_block.get("first_name") or data_block.get("first")
        last_name = data_block.get("last_name") or data_block.get("last")
        name_val = data_block.get("registrant_name") or data_block.get("name")

        if isinstance(name_val, dict):
            first_name = name_val.get("first") or name_val.get("first_name") or first_name
            last_name = name_val.get("last") or name_val.get("last_name") or last_name
        elif isinstance(name_val, str) and not first_name and not last_name:
            parts = name_val.strip().split(None, 1)
            if len(parts) == 2:
                first_name, last_name = parts
            else:
                first_name = name_val

        # Extract Poster Details
        poster_title = data_block.get("poster_title")
        faculty_adviser_name = data_block.get("faculty_adviser_name")
        poster_presentation_abstract = data_block.get("poster_presentation_abstract")

        # Compile and assign to class variables
        return {
            "email_address": email_address,
            "first_name": first_name,
            "last_name": last_name,
            "presenting_poster": presenting_poster,
            "poster_title": poster_title,
            "faculty_adviser_name": faculty_adviser_name,
            "poster_presentation_abstract": poster_presentation_abstract,
            "sid": int(sid) if sid is not None else None,
            "serial": int(serial) if serial is not None else None
        }

class PresenterResponse(BaseModel):
    id: str
    email_address: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    poster_title: Optional[str] = None
    faculty_adviser_name: Optional[str] = None
    poster_presentation_abstract: Optional[str] = None
    drupal_sid: Optional[int] = None
    serial_number: Optional[int] = None
    is_visible: bool
    registered_at: datetime.datetime

    class Config:
        from_attributes = True


class NametagsWebhookPayload(BaseModel):
    email_address: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    home_institution_or_organization: Optional[str] = None
    attendee_status: Optional[str] = None
    student: Optional[str] = None
    t_shirt_size: Optional[str] = None
    presenting_poster: Optional[str] = None
    lodging: Optional[str] = None
    gender_identity: Optional[str] = None
    roommate_preference: Optional[str] = None
    identified_roommate: Optional[str] = None
    sid: Optional[int] = None
    serial: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def parse_drupal_payload(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        # Locate the data block (Drupal Remote Post wraps submissions in "data")
        data_block = values.get("data")
        if not isinstance(data_block, dict):
            data_block = values

        # Extract SID and Serial
        sid = values.get("sid") or data_block.get("sid") or data_block.get("submission_id")
        serial = values.get("serial") or data_block.get("serial") or data_block.get("serial_number")

        # Extract Email Address
        email_val = data_block.get("email_address") or data_block.get("email") or data_block.get("mail")
        email_address = None
        if isinstance(email_val, dict):
            email_address = email_val.get("mail_1") or email_val.get("email") or email_val.get("value")
        elif isinstance(email_val, str):
            email_address = email_val

        if email_address:
            email_address = email_address.strip().lower()

        # Extract Name
        first_name = data_block.get("first_name") or data_block.get("first")
        last_name = data_block.get("last_name") or data_block.get("last")
        name_val = data_block.get("registrant_name") or data_block.get("name")

        if isinstance(name_val, dict):
            first_name = name_val.get("first") or name_val.get("first_name") or first_name
            last_name = name_val.get("last") or name_val.get("last_name") or last_name
        elif isinstance(name_val, str) and not first_name and not last_name:
            parts = name_val.strip().split(None, 1)
            if len(parts) == 2:
                first_name, last_name = parts
            else:
                first_name = name_val

        # Extract Other Fields
        home_institution_or_organization = data_block.get("home_institution_or_organization")
        attendee_status = data_block.get("attendee_status")
        student = data_block.get("student")
        t_shirt_size = data_block.get("t_shirt_size")
        presenting_poster = data_block.get("presenting_poster")

        # Extract Lodging Fields
        lodging = data_block.get("lodging")
        
        # Gender Identity handles strings & composite select_other Drupal formats
        gender_val = data_block.get("gender_identity")
        gender_identity = None
        if isinstance(gender_val, dict):
            sel = gender_val.get("select")
            oth = gender_val.get("other")
            if sel == "_other_" or not sel:
                gender_identity = oth
            else:
                gender_identity = sel
        elif isinstance(gender_val, str):
            gender_identity = gender_val
            
        roommate_preference = data_block.get("roommate_preference")
        identified_roommate = data_block.get("identified_roommate")

        return {
            "email_address": email_address,
            "first_name": first_name,
            "last_name": last_name,
            "home_institution_or_organization": home_institution_or_organization,
            "attendee_status": attendee_status,
            "student": student,
            "t_shirt_size": t_shirt_size,
            "presenting_poster": presenting_poster,
            "lodging": lodging,
            "gender_identity": gender_identity,
            "roommate_preference": roommate_preference,
            "identified_roommate": identified_roommate,
            "sid": int(sid) if sid is not None else None,
            "serial": int(serial) if serial is not None else None
        }


class RegistrantResponse(BaseModel):
    id: str
    email_address: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    home_institution_or_organization: Optional[str] = None
    attendee_status: Optional[str] = None
    student: Optional[str] = None
    t_shirt_size: Optional[str] = None
    presenting_poster: Optional[str] = None
    drupal_sid: Optional[int] = None
    serial_number: Optional[int] = None
    registered_at: datetime.datetime
    
    # Lodging Extension Fields
    lodging: Optional[str] = None
    gender_identity: Optional[str] = None
    roommate_preference: Optional[str] = None
    identified_roommate: Optional[str] = None
    room_id: Optional[str] = None

    class Config:
        from_attributes = True


class RoomResponse(BaseModel):
    id: str
    name: str
    capacity: int
    room_gender: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class RoomCreate(BaseModel):
    name: str
    capacity: int = 2
    room_gender: str = "Any"


class RoomAssignmentPayload(BaseModel):
    registrant_id: str
    room_id: Optional[str] = None
