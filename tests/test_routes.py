import pytest
from fastapi import status
from backend.models import Presenter

def test_root_endpoints(client):
    # Test that / and /index.html return HTML content
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    assert "Poster Presenters" in response.text

    response = client.get("/index.html")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]

def test_webhook_unauthorized(client):
    # Test webhook without headers
    response = client.post("/api/drupal-webhook", json={"email_address": "test@example.com"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # Test webhook with incorrect header token
    response = client.post(
        "/api/drupal-webhook", 
        json={"email_address": "test@example.com"},
        headers={"X-Drupal-Webhook-Token": "bad_token"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

def test_webhook_validation_failures(client):
    # Test webhook with missing email address
    response = client.post(
        "/api/drupal-webhook",
        json={"first_name": "John"},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    # The endpoint validates email_address exists in payload
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

def test_webhook_non_presenter_ignored(client):
    # Submission with presenting_poster = "No" should be ignored
    payload = {
        "email_address": "nonpresenter@example.com",
        "first_name": "Bob",
        "last_name": "Smith",
        "presenting_poster": "No",
        "poster_title": "Why I am not presenting",
        "faculty_adviser_name": "Dr. Adviser",
        "poster_presentation_abstract": "No abstract"
    }
    response = client.post(
        "/api/drupal-webhook",
        json={"data": payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ignored"

def test_webhook_presenter_upsert(client, db_session):
    # 1. Test insertion of new presenter
    payload = {
        "registrant_name": {"first": "Alice", "last": "Johnson"},
        "email_address": "alice@example.com",
        "presenting_poster": "Yes",
        "poster_title": "Quantum Chaos",
        "faculty_adviser_name": "Dr. Heisenberg",
        "poster_presentation_abstract": "An abstract details.",
        "sid": 101,
        "serial": 5
    }
    response = client.post(
        "/api/drupal-webhook",
        json={"data": payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert "id" in data

    # Verify database state
    presenter = db_session.query(Presenter).filter(Presenter.email_address == "alice@example.com").first()
    assert presenter is not None
    assert presenter.first_name == "Alice"
    assert presenter.last_name == "Johnson"
    assert presenter.poster_title == "Quantum Chaos"
    assert presenter.is_visible is True

    # 2. Test updating existing presenter (upsert)
    update_payload = {
        "registrant_name": {"first": "Alice", "last": "Johnson"},
        "email_address": "alice@example.com",
        "presenting_poster": "Yes",
        "poster_title": "Super-Symmetric Quantum Chaos", # Modified Title
        "faculty_adviser_name": "Dr. Heisenberg",
        "poster_presentation_abstract": "An abstract details.",
        "sid": 101,
        "serial": 5
    }
    response = client.post(
        "/api/drupal-webhook",
        json={"data": update_payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    
    # Verify title was updated in database
    db_session.expire_all()
    presenter = db_session.query(Presenter).filter(Presenter.email_address == "alice@example.com").first()
    assert presenter.poster_title == "Super-Symmetric Quantum Chaos"

def test_webhook_toggle_visibility(client, db_session):
    # Create an initial presenter
    p = Presenter(
        id="test-uuid",
        email_address="toggle@example.com",
        first_name="Jane",
        last_name="Doe",
        poster_title="Title",
        faculty_adviser_name="Adviser",
        poster_presentation_abstract="Abstract",
        is_visible=True
    )
    db_session.add(p)
    db_session.commit()

    # Send webhook where presenting_poster is "No"
    payload = {
        "email_address": "toggle@example.com",
        "presenting_poster": "No"
    }
    response = client.post(
        "/api/drupal-webhook",
        json={"data": payload},
        headers={"X-Drupal-Webhook-Token": "test_webhook_token"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"
    
    # Verify is_visible is now False
    db_session.expire_all()
    presenter = db_session.query(Presenter).filter(Presenter.email_address == "toggle@example.com").first()
    assert presenter.is_visible is False

def test_list_presenters_sorting(client, db_session):
    # Insert multiple presenters in random alphabetical order
    p1 = Presenter(id="1", email_address="z@example.com", first_name="Zack", last_name="Zeta", poster_title="T1", is_visible=True)
    p2 = Presenter(id="2", email_address="a@example.com", first_name="Abby", last_name="Alpha", poster_title="T2", is_visible=True)
    p3 = Presenter(id="3", email_address="m@example.com", first_name="Mary", last_name="Beta", poster_title="T3", is_visible=True)
    p4 = Presenter(id="4", email_address="h@example.com", first_name="Hidden", last_name="Hide", poster_title="T4", is_visible=False) # Invisible
    
    db_session.add_all([p1, p2, p3, p4])
    db_session.commit()

    # Query public presenters API
    response = client.get("/api/presenters")
    assert response.status_code == status.HTTP_200_OK
    presenters = response.json()

    # Assert that only visible presenters are returned
    assert len(presenters) == 3
    
    # Assert they are sorted by last name: Alpha, Beta, Zeta
    assert presenters[0]["last_name"] == "Alpha"
    assert presenters[1]["last_name"] == "Beta"
    assert presenters[2]["last_name"] == "Zeta"

def test_rss_feed_generation(client, db_session):
    # Insert multiple presenters in random alphabetical order
    p1 = Presenter(id="1", email_address="z@example.com", first_name="Zack", last_name="Zeta", poster_title="Quantum Physics", faculty_adviser_name="Adviser Z", poster_presentation_abstract="Abstract Z", is_visible=True)
    p2 = Presenter(id="2", email_address="a@example.com", first_name="Abby", last_name="Alpha", poster_title="Astrophysics", faculty_adviser_name="Adviser A", poster_presentation_abstract="Abstract A", is_visible=True)
    p3 = Presenter(id="3", email_address="h@example.com", first_name="Hidden", last_name="Hide", poster_title="Hidden Physics", faculty_adviser_name="Adviser H", poster_presentation_abstract="Abstract H", is_visible=False) # Invisible
    
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    # Query public feed endpoint
    response = client.get("/feed.xml")
    assert response.status_code == status.HTTP_200_OK
    assert "application/rss+xml" in response.headers["content-type"]
    
    # Assert RSS XML output has correct elements
    xml_text = response.text
    assert "<rss version=\"2.0\"" in xml_text
    assert "<channel>" in xml_text
    assert "<title>CAARMS 2026 Poster Presenters</title>" in xml_text
    
    # Should include visible presenter details without presenter name in title
    assert "<title>Astrophysics</title>" in xml_text
    assert "<title>Quantum Physics</title>" in xml_text
    
    # Should link to query parameter version of page rather than hash anchor
    assert "/?presenter=2" in xml_text
    assert "/?presenter=1" in xml_text
    
    # Description should contain the forced line break before Faculty Adviser and bold labels
    assert "&lt;strong&gt;Presenter:&lt;/strong&gt; Abby Alpha&lt;br/&gt;\n&lt;strong&gt;Faculty Adviser:&lt;/strong&gt; Adviser A" in xml_text
    
    # Should NOT contain the abstracts anywhere in the RSS feed
    assert "Abstract A" not in xml_text
    assert "Abstract Z" not in xml_text
    
    # Should NOT include invisible presenter details
    assert "Hidden Physics" not in xml_text
    
    # The order of items in XML string should reflect alphabetical ordering by last name: Alpha then Zeta
    idx_alpha = xml_text.find("Alpha")
    idx_zeta = xml_text.find("Zeta")
    assert idx_alpha < idx_zeta

