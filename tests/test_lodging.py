import pytest
from fastapi import status
from backend.models import Registrant, Room, Presenter

def test_nametags_webhook_lodging_fields(client, db_session):
    # Test valid ingestion with flat lodging fields
    payload = {
        "email_address": "student1@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "home_institution_or_organization": "Harvard University",
        "attendee_status": "Attendee",
        "student": "Yes",
        "t_shirt_size": "USML",
        "presenting_poster": "No",
        "lodging": "Yes",
        "gender_identity": "Woman",
        "roommate_preference": "Require Same Gender",
        "identified_roommate": "Bob Jones",
        "sid": 2001,
        "serial": 21
    }

    response = client.post(
        "/api/nametags-lodging-webhook",
        json={"data": payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"

    db_session.expire_all()
    reg = db_session.query(Registrant).filter(Registrant.email_address == "student1@example.com").first()
    assert reg is not None
    assert reg.lodging == "Yes"
    assert reg.gender_identity == "Woman"
    assert reg.roommate_preference == "Require Same Gender"
    assert reg.identified_roommate == "Bob Jones"

def test_nametags_webhook_composite_gender_identity(client, db_session):
    # Drupal select_other submits either select value or select == _other_ and other value
    payload_select = {
        "email_address": "student2@example.com",
        "lodging": "Yes",
        "gender_identity": {"select": "Man", "other": ""},
        "roommate_preference": "Prefer Same Gender",
        "identified_roommate": ""
    }

    response = client.post(
        "/api/nametags-webhook",
        json={"data": payload_select},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK

    db_session.expire_all()
    reg = db_session.query(Registrant).filter(Registrant.email_address == "student2@example.com").first()
    assert reg.gender_identity == "Man"

    # Test "other" path
    payload_other = {
        "email_address": "student3@example.com",
        "lodging": "Yes",
        "gender_identity": {"select": "_other_", "other": "Non-binary fluid"},
        "roommate_preference": "Prefer Same Gender",
        "identified_roommate": ""
    }

    response = client.post(
        "/api/nametags-webhook",
        json={"data": payload_other},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK

    db_session.expire_all()
    reg = db_session.query(Registrant).filter(Registrant.email_address == "student3@example.com").first()
    assert reg.gender_identity == "Non-binary fluid"

def test_admin_rooms_crud(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # 1. Create Room (Unauthorized)
    response = client.post("/api/admin/rooms", json={"name": "101", "capacity": 2, "room_gender": "Man"})
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # 2. Create Room (Authorized)
    response = client.post(
        "/api/admin/rooms",
        json={"name": "101", "capacity": 2, "room_gender": "Man"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    room_data = response.json()
    assert room_data["name"] == "101"
    assert room_data["capacity"] == 2
    assert room_data["room_gender"] == "Man"
    assert "id" in room_data

    # 3. Create Duplicate Room Name (fails)
    response = client.post(
        "/api/admin/rooms",
        json={"name": "101", "capacity": 2, "room_gender": "Woman"},
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # 4. List Rooms
    response = client.get("/api/admin/rooms", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    rooms = response.json()
    assert len(rooms) == 1
    assert rooms[0]["name"] == "101"

    # 5. Delete Room
    room_id = room_data["id"]
    response = client.delete(f"/api/admin/rooms/{room_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    # Verify deleted
    response = client.get("/api/admin/rooms", headers=headers)
    assert len(response.json()) == 0

def test_admin_lodging_registrants(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # Insert registrants with and without lodging requests
    r1 = Registrant(id="r1", email_address="r1@example.com", lodging="Yes")
    r2 = Registrant(id="r2", email_address="r2@example.com", lodging="yes")
    r3 = Registrant(id="r3", email_address="r3@example.com", lodging="No")
    r4 = Registrant(id="r4", email_address="r4@example.com") # None
    db_session.add_all([r1, r2, r3, r4])
    db_session.commit()

    # Query
    response = client.get("/api/admin/lodging/registrants", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    emails = [r["email_address"] for r in data]
    assert "r1@example.com" in emails
    assert "r2@example.com" in emails

def test_room_assign_and_capacity_constraints(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # Insert room with capacity 1
    room = Room(id="room-single", name="Single 1", capacity=1, room_gender="Any")
    
    # Insert registrants
    reg1 = Registrant(id="reg1", email_address="reg1@example.com", lodging="Yes")
    reg2 = Registrant(id="reg2", email_address="reg2@example.com", lodging="Yes")
    db_session.add_all([room, reg1, reg2])
    db_session.commit()

    # 1. Assign first registrant (should succeed)
    response = client.post(
        "/api/admin/rooms/assign",
        json={"registrant_id": "reg1", "room_id": "room-single"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK

    db_session.expire_all()
    reg1_db = db_session.query(Registrant).filter(Registrant.id == "reg1").first()
    assert reg1_db.room_id == "room-single"

    # 2. Assign second registrant (should fail because capacity is 1)
    response = client.post(
        "/api/admin/rooms/assign",
        json={"registrant_id": "reg2", "room_id": "room-single"},
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "capacity" in response.json()["detail"]

    # 3. Unassign first registrant (set room_id to None/null)
    response = client.post(
        "/api/admin/rooms/assign",
        json={"registrant_id": "reg1", "room_id": None},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK

    db_session.expire_all()
    reg1_db = db_session.query(Registrant).filter(Registrant.id == "reg1").first()
    assert reg1_db.room_id is None

def test_delete_room_clears_registrant_assignments(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # Insert room and occupants
    room = Room(id="room-todelete", name="Delete Me", capacity=2, room_gender="Any")
    reg = Registrant(id="reg-assigned", email_address="assigned@example.com", lodging="Yes", room_id="room-todelete")
    db_session.add_all([room, reg])
    db_session.commit()

    # Verify assigned in DB
    reg_db = db_session.query(Registrant).filter(Registrant.id == "reg-assigned").first()
    assert reg_db.room_id == "room-todelete"

    # Delete the room
    response = client.delete("/api/admin/rooms/room-todelete", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    # Verify registrant's room_id is cleared
    db_session.expire_all()
    reg_db = db_session.query(Registrant).filter(Registrant.id == "reg-assigned").first()
    assert reg_db.room_id is None


def test_remove_dissy_endpoint(client, db_session):
    # Insert dummy records
    reg = Registrant(id="dissy-reg", email_address="dissy022@gmailcom")
    pres = Presenter(id="dissy-pres", email_address="dissy022@gmailcom", first_name="Dissy", last_name="Test")
    db_session.add_all([reg, pres])
    db_session.commit()
    
    # Test unauthorized
    response = client.post("/api/admin/remove-dissy")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    # Test authorized
    response = client.post(
        "/api/admin/remove-dissy",
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["registrants_deleted"] == 1
    assert data["presenters_deleted"] == 1
    
    # Verify deleted in DB
    db_session.expire_all()
    assert db_session.query(Registrant).filter(Registrant.email_address == "dissy022@gmailcom").first() is None
    assert db_session.query(Presenter).filter(Presenter.email_address == "dissy022@gmailcom").first() is None
