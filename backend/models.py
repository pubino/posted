import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from backend.database import Base

class Presenter(Base):
    __tablename__ = "presenters"

    id = Column(String, primary_key=True, index=True)  # Store UUID as string
    email_address = Column(String, unique=True, index=True, nullable=False)  # Lowercase for case-insensitivity
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    poster_title = Column(String, nullable=True)
    faculty_adviser_name = Column(String, nullable=True)
    poster_presentation_abstract = Column(String, nullable=True)
    drupal_sid = Column(Integer, nullable=True)
    serial_number = Column(Integer, nullable=True)
    is_visible = Column(Boolean, default=True, nullable=False)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)


class Registrant(Base):
    __tablename__ = "registrants"

    id = Column(String, primary_key=True, index=True)
    email_address = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    home_institution_or_organization = Column(String, nullable=True)
    attendee_status = Column(String, nullable=True)
    student = Column(String, nullable=True)
    t_shirt_size = Column(String, nullable=True)
    presenting_poster = Column(String, nullable=True)
    drupal_sid = Column(Integer, nullable=True)
    serial_number = Column(Integer, nullable=True)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)
