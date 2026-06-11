import pytest
from fastapi import status
from backend.models import Registrant, Room

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

def test_room_details_update(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # Insert room
    room = Room(id="room-details", name="Details Room", capacity=2, room_gender="Any")
    room_occupied = Room(id="room-occupied", name="Occupied Room", capacity=2, room_gender="Any")
    reg = Registrant(id="reg-occ", email_address="occ@example.com", lodging="Yes", room_id="room-occupied")
    db_session.add_all([room, room_occupied, reg])
    db_session.commit()

    # 1. Update Room details (Unauthorized)
    response = client.patch(
        "/api/admin/rooms/room-details",
        json={"held_by": "Dr. Massey", "comments": "Temporary block"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # 2. Update Room details (Authorized - update all fields of unoccupied room)
    response = client.patch(
        "/api/admin/rooms/room-details",
        json={
            "held_by": "Dr. Massey",
            "comments": "Temporary block",
            "name": "Updated Details Room",
            "capacity": 3,
            "room_gender": "Woman"
        },
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["held_by"] == "Dr. Massey"
    assert data["comments"] == "Temporary block"
    assert data["name"] == "Updated Details Room"
    assert data["capacity"] == 3
    assert data["room_gender"] == "Woman"

    # Verify db state
    db_session.expire_all()
    room_db = db_session.query(Room).filter(Room.id == "room-details").first()
    assert room_db.held_by == "Dr. Massey"
    assert room_db.comments == "Temporary block"
    assert room_db.name == "Updated Details Room"
    assert room_db.capacity == 3
    assert room_db.room_gender == "Woman"

    # 3. Try to update name/capacity/gender of occupied room (should fail)
    response = client.patch(
        "/api/admin/rooms/room-occupied",
        json={
            "name": "New Name",
            "capacity": 4,
            "room_gender": "Man"
        },
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot edit" in response.json()["detail"]

    # 4. Try to update name of unoccupied room to an existing room name (should fail)
    response = client.patch(
        "/api/admin/rooms/room-details",
        json={"name": "Occupied Room"},
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in response.json()["detail"]


def test_lodging_write_ins_and_promotions(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # 1. Create a webhook registrant (not requesting lodging)
    webhook_reg = Registrant(
        id="webhook-reg-1",
        email_address="webhook@example.com",
        first_name="Web",
        last_name="Hook",
        lodging="No",
        drupal_sid=123,
        serial_number=456,
        is_write_in=False
    )
    db_session.add(webhook_reg)
    db_session.commit()

    # Verify they appear in non-lodging list
    response = client.get("/api/admin/registrants/non-lodging", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 1
    non_lodging_emails = [r["email_address"] for r in data]
    assert "webhook@example.com" in non_lodging_emails

    # 2. Promote them via PATCH
    response = client.patch(
        "/api/admin/registrants/webhook-reg-1/lodging",
        json={"needs_lodging": True},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    
    db_session.expire_all()
    reg_db = db_session.query(Registrant).filter(Registrant.id == "webhook-reg-1").first()
    assert reg_db.lodging == "Yes"
    assert reg_db.is_write_in is True

    # 3. Create a manual guest write-in via POST
    response = client.post(
        "/api/admin/lodging/registrants",
        json={
            "first_name": "Manual",
            "last_name": "Guest",
            "email_address": "manual@example.com",
            "gender_identity": "Man",
            "roommate_preference": "Prefer Same Gender",
            "identified_roommate": "Web Hook"
        },
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    manual_data = response.json()
    assert manual_data["is_write_in"] is True
    assert manual_data["lodging"] == "Yes"
    assert manual_data["drupal_sid"] is None
    manual_id = manual_data["id"]

    # 4. Verify both appear in lodging registrants list
    response = client.get("/api/admin/lodging/registrants", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    lodging_data = response.json()
    lodging_emails = [r["email_address"] for r in lodging_data]
    assert "webhook@example.com" in lodging_emails
    assert "manual@example.com" in lodging_emails

    # 5. Delete/Revert promoted registrant
    response = client.delete(f"/api/admin/lodging/registrants/webhook-reg-1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["action"] == "reverted"

    # Verify they still exist in database, but reverted
    db_session.expire_all()
    reg_db = db_session.query(Registrant).filter(Registrant.id == "webhook-reg-1").first()
    assert reg_db is not None
    assert reg_db.lodging == "No"
    assert reg_db.is_write_in is False

    # 6. Delete manual write-in
    response = client.delete(f"/api/admin/lodging/registrants/{manual_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["action"] == "deleted"

    # Verify they are permanently deleted from database
    db_session.expire_all()
    reg_db = db_session.query(Registrant).filter(Registrant.id == manual_id).first()
    assert reg_db is None


def test_room_category(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # 1. Create room with category
    response = client.post(
        "/api/admin/rooms",
        json={"name": "201", "capacity": 2, "room_gender": "Any", "category": "Speaker Room"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["category"] == "Speaker Room"
    room_id = data["id"]

    # 2. Verify in DB
    db_session.expire_all()
    room_db = db_session.query(Room).filter(Room.id == room_id).first()
    assert room_db.category == "Speaker Room"

    # 3. Update category via PATCH
    response = client.patch(
        f"/api/admin/rooms/{room_id}",
        json={"category": "Student Room"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["category"] == "Student Room"

    # 4. Clear category
    response = client.patch(
        f"/api/admin/rooms/{room_id}",
        json={"category": "None"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["category"] is None


def test_room_reordering(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # 1. Create three rooms
    r1 = client.post("/api/admin/rooms", json={"name": "A", "capacity": 2}, headers=headers).json()
    r2 = client.post("/api/admin/rooms", json={"name": "B", "capacity": 2}, headers=headers).json()
    r3 = client.post("/api/admin/rooms", json={"name": "C", "capacity": 2}, headers=headers).json()

    # Verify default sort (order by name or sort_order)
    response = client.get("/api/admin/rooms", headers=headers)
    names = [r["name"] for r in response.json()]
    assert names == ["A", "B", "C"]

    # 2. Reorder rooms: B, C, A
    reorder_payload = {"room_ids": [r2["id"], r3["id"], r1["id"]]}
    response = client.post("/api/admin/rooms/reorder", json=reorder_payload, headers=headers)
    assert response.status_code == status.HTTP_200_OK

    # 3. Verify sorted listing
    response = client.get("/api/admin/rooms", headers=headers)
    names = [r["name"] for r in response.json()]
    assert names == ["B", "C", "A"]


def test_bulk_room_creation(client, db_session):
    headers = {"X-MS-CLIENT-PRINCIPAL-NAME": "bino@princeton.edu"}

    # 1. Create bulk rooms with incrementing trailing digits
    response = client.post(
        "/api/admin/rooms/bulk",
        json={"base_name": "Room 108", "count": 3, "capacity": 2, "room_gender": "Woman", "category": "Student Room"},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 3
    assert data[0]["name"] == "Room 108"
    assert data[1]["name"] == "Room 109"
    assert data[2]["name"] == "Room 110"
    for r in data:
        assert r["capacity"] == 2
        assert r["room_gender"] == "Woman"
        assert r["category"] == "Student Room"

    # 2. Try creating duplicate names (should fail)
    response = client.post(
        "/api/admin/rooms/bulk",
        json={"base_name": "Room 109", "count": 2, "capacity": 2},
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exist" in response.json()["detail"].lower()

    # 3. Create bulk rooms without trailing digits
    response = client.post(
        "/api/admin/rooms/bulk",
        json={"base_name": "Speaker Suite", "count": 2, "capacity": 1},
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    data2 = response.json()
    assert len(data2) == 2
    assert data2[0]["name"] == "Speaker Suite 1"
    assert data2[1]["name"] == "Speaker Suite 2"


