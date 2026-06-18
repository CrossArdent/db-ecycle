from datetime import datetime, timedelta, timezone

from models import create_job, get_db, get_job, init_db, mark_completed
from tests.conftest import create_job_via_form, login


def test_display_role_cannot_create_or_edit(client):
    login(client, "display", "change-me-display")

    response = client.get("/jobs/new")
    assert response.status_code == 403

    response = client.post("/jobs/1/action", data={"action": "complete", "csrf_token": "bad"})
    assert response.status_code in {400, 403}


def test_tv_shows_active_jobs_and_only_recent_completed_jobs(app, client):
    with app.app_context():
        released_id = create_job(
            {
                "order_number": "CL-TV-READY",
                "customer_name": "Ready Customer",
                "date_received": "2026-06-10",
                "release_status": "Released",
                "notes": "",
            },
            "admin",
        )
        held_id = create_job(
            {
                "order_number": "CL-TV-HOLD",
                "customer_name": "Hold Customer",
                "date_received": "2026-06-11",
                "release_status": "On Hold",
                "notes": "",
            },
            "admin",
        )
        recent_id = create_job(
            {
                "order_number": "CL-TV-RECENT",
                "customer_name": "Recent Customer",
                "date_received": "2026-06-12",
                "release_status": "Released",
                "notes": "",
            },
            "admin",
        )
        old_id = create_job(
            {
                "order_number": "CL-TV-OLD",
                "customer_name": "Old Customer",
                "date_received": "2026-06-01",
                "release_status": "Released",
                "notes": "",
            },
            "admin",
        )
        mark_completed(get_job(recent_id), "warehouse")
        mark_completed(get_job(old_id), "warehouse")
        old_completed_at = (datetime.now(timezone.utc) - timedelta(days=8)).replace(microsecond=0).isoformat()
        get_db().execute(
            "UPDATE jobs SET completed_at = ? WHERE id = ?",
            (old_completed_at, old_id),
        )
        get_db().commit()

    login(client, "display", "change-me-display")
    response = client.get("/tv")
    assert b"CL-TV-READY" in response.data
    assert b"CL-TV-HOLD" in response.data
    assert b"CL-TV-RECENT" in response.data
    assert b"CL-TV-OLD" not in response.data

    client.get("/logout")
    login(client, "admin", "change-me-admin")
    response = client.get("/completed")
    assert b"CL-TV-RECENT" in response.data
    assert b"CL-TV-OLD" in response.data


def test_status_changes_create_audit_entries(app, client):
    login(client, "account", "change-me-account")
    create_job_via_form(client, "CL-AUDIT-1", release_status="On Hold")

    with app.app_context():
        entries = get_db().execute(
            "SELECT field_changed, new_value FROM audit_log WHERE order_number = ? ORDER BY id",
            ("CL-AUDIT-1",),
        ).fetchall()
        assert ("job", "created") in [(row["field_changed"], row["new_value"]) for row in entries]
