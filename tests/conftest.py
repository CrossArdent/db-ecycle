import re

import pytest

from app import create_app
from models import init_db, seed_default_users


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "test.sqlite3"),
            "SECRET_KEY": "test-secret",
            "SMTP_HOST": "",
            "SMTP_FROM": "",
            "WAREHOUSE_MANAGER_EMAIL": "",
        }
    )
    with app.app_context():
        init_db()
        seed_default_users()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_token(response):
    text = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match, text
    return match.group(1)


def login(client, username, password):
    response = client.get("/login")
    token = csrf_token(response)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )


def logout(client):
    return client.get("/logout", follow_redirects=True)


def create_job_via_form(client, order_number, release_status="Released", customer_name="Acme Recycling"):
    response = client.get("/jobs/new")
    token = csrf_token(response)
    return client.post(
        "/jobs/new",
        data={
            "order_number": order_number,
            "customer_name": customer_name,
            "date_received": "2026-06-10",
            "release_status": release_status,
            "notes": "Test job",
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def post_job_action(client, job_id, action):
    response = client.get(f"/jobs/{job_id}/edit")
    token = csrf_token(response)
    return client.post(
        f"/jobs/{job_id}/action",
        data={"action": action, "csrf_token": token},
        follow_redirects=True,
    )
