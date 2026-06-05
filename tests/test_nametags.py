import pytest
from fastapi import status
import os
from backend.models import Registrant
from backend.config import settings

def test_nametags_webhook_unauthorized(client):
    # Test webhook without token
    response = client.post("/api/nametags-webhook", json={"email_address": "unauth@example.com"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # Test webhook with bad token
    response = client.post(
        "/api/nametags-webhook",
        json={"email_address": "unauth@example.com"},
        headers={"X-Drupal-Webhook-Token": "bad_token"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

def test_nametags_webhook_ingest_and_upsert(client, db_session):
    # Test valid ingestion
    payload = {
        "email_address": "attendee@example.com",
        "first_name": "Jhevon",
        "last_name": "Smith",
        "home_institution_or_organization": "Princeton University",
        "attendee_status": "Attendee",
        "student": "Yes",
        "t_shirt_size": "UMED",
        "presenting_poster": "Yes",
        "sid": 1234,
        "serial": 45
    }

    response = client.post(
        "/api/nametags-webhook",
        json={"data": payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}  # In test settings, this maps to Settings token
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"

    # Verify db record
    db_session.expire_all()
    reg = db_session.query(Registrant).filter(Registrant.email_address == "attendee@example.com").first()
    assert reg is not None
    assert reg.first_name == "Jhevon"
    assert reg.last_name == "Smith"
    assert reg.home_institution_or_organization == "Princeton University"
    assert reg.t_shirt_size == "UMED"
    assert reg.presenting_poster == "Yes"

    # Test updating/upserting existing record
    update_payload = payload.copy()
    update_payload["t_shirt_size"] = "ULRG"  # Change size
    update_payload["attendee_status"] = "Speaker"

    response = client.post(
        "/api/nametags-webhook",
        json={"data": update_payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK

    db_session.expire_all()
    reg = db_session.query(Registrant).filter(Registrant.email_address == "attendee@example.com").first()
    assert reg.t_shirt_size == "ULRG"
    assert reg.attendee_status == "Speaker"

def test_admin_auth_forbidden(client):
    # Missing principal headers should redirect to login
    response = client.get("/admin/nametags", follow_redirects=False)
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT

    response = client.get("/api/admin/registrants")
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Unauthorized principal header
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "attacker@princeton.edu"}
    response = client.get("/admin/nametags", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN

def test_admin_auth_allowed(client, db_session):
    # Add dummy registrant
    r = Registrant(
        id="dummy-uuid",
        email_address="reg@example.com",
        first_name="Jane",
        last_name="Doe",
        home_institution_or_organization="Orfe Dept",
        attendee_status="Speaker"
    )
    db_session.add(r)
    db_session.commit()

    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}
    
    # Check page access
    response = client.get("/admin/nametags", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "Nametag Generator" in response.text

    # Check API access
    response = client.get("/api/admin/registrants", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 1
    assert data[0]["email_address"] == "reg@example.com"
    assert data[0]["home_institution_or_organization"] == "Orfe Dept"

def test_logo_upload(client):
    # Prepare dummy file
    import io
    file_content = b"fake-png-content"
    file = io.BytesIO(file_content)
    
    # Unauthorized
    response = client.post(
        "/api/admin/upload-logo",
        data={"logo_type": "primary"},
        files={"file": ("test.png", file, "image/png")}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Authorized upload
    file.seek(0)
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}
    response = client.post(
        "/api/admin/upload-logo",
        data={"logo_type": "primary"},
        files={"file": ("test.png", file, "image/png")},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"
    assert "badge_primary_custom.png" in response.json()["url"]

    # Verify file saved on disk
    assert os.path.exists("frontend/static/images/badge_primary_custom.png")
    
    # Clean up uploaded file
    if os.path.exists("frontend/static/images/badge_primary_custom.png"):
        os.remove("frontend/static/images/badge_primary_custom.png")
