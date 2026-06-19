from models import (
    DEFAULT_USERS,
    ON_HOLD,
    RELEASED,
    RESALE_NOT_NEEDED,
    RESALE_PROVIDED,
    RESALE_REQUESTED,
    get_db,
    get_job,
    mark_completed,
)
from tests.conftest import create_job_via_form, login, logout, post_job_action


PASSWORDS = {user["username"]: user["password"] for user in DEFAULT_USERS}
ADMIN = "andy.admin"
ACCOUNT = "account.demo"
WAREHOUSE = "warehouse.manager"
DISPLAY = "warehouse.tv"


def job_by_order(order_number):
    return get_db().execute("SELECT * FROM jobs WHERE order_number = ?", (order_number,)).fetchone()


def test_new_jobs_default_to_resale_not_needed(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-RESALE-DEFAULT")

    with app.app_context():
        assert job_by_order("CL-RESALE-DEFAULT")["resale_status"] == RESALE_NOT_NEEDED


def test_account_manager_can_request_and_cancel_resale_numbers(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-RESALE-CANCEL")

    with app.app_context():
        job_id = job_by_order("CL-RESALE-CANCEL")["id"]

    response = post_job_action(client, job_id, "request_resale")
    assert b"Resale numbers requested" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["resale_status"] == RESALE_REQUESTED
        assert job["resale_requested_by"] == "Demo Account Manager"

    response = post_job_action(client, job_id, "cancel_resale")
    assert b"Resale request cancelled" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["resale_status"] == RESALE_NOT_NEEDED
        assert job["resale_requested_at"] is None
        assert job["resale_requested_by"] is None


def test_account_manager_cannot_provide_resale_numbers(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-RESALE-PROVIDE-BLOCK")

    with app.app_context():
        job_id = job_by_order("CL-RESALE-PROVIDE-BLOCK")["id"]

    post_job_action(client, job_id, "request_resale")
    response = post_job_action(client, job_id, "provide_resale")
    assert response.status_code == 403

    with app.app_context():
        assert get_job(job_id)["resale_status"] == RESALE_REQUESTED


def test_warehouse_manager_can_view_queue_and_provide_resale_numbers(app, client):
    login(client, WAREHOUSE, PASSWORDS[WAREHOUSE])
    create_job_via_form(client, "CL-RESALE-WH")

    with app.app_context():
        job_id = job_by_order("CL-RESALE-WH")["id"]

    post_job_action(client, job_id, "request_resale")
    response = client.get("/resale-needed")
    assert response.status_code == 200
    assert b"CL-RESALE-WH" in response.data

    response = post_job_action(client, job_id, "provide_resale")
    assert b"Resale numbers marked provided" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["resale_status"] == RESALE_PROVIDED
        assert job["resale_provided_by"] == "Warehouse Manager"


def test_warehouse_display_cannot_access_resale_actions(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-RESALE-DISPLAY")

    with app.app_context():
        job_id = job_by_order("CL-RESALE-DISPLAY")["id"]

    logout(client)
    login(client, DISPLAY, PASSWORDS[DISPLAY])
    response = client.get("/resale-needed")
    assert response.status_code == 403

    response = client.post(f"/jobs/{job_id}/action", data={"action": "request_resale"})
    assert response.status_code == 403


def test_resale_status_changes_do_not_affect_release_status(app, client):
    login(client, WAREHOUSE, PASSWORDS[WAREHOUSE])
    create_job_via_form(client, "CL-RESALE-HOLD", release_status=ON_HOLD)

    with app.app_context():
        job_id = job_by_order("CL-RESALE-HOLD")["id"]

    post_job_action(client, job_id, "request_resale")

    with app.app_context():
        job = get_job(job_id)
        assert job["resale_status"] == RESALE_REQUESTED
        assert job["release_status"] == ON_HOLD


def test_release_status_changes_do_not_affect_resale_status(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-RELEASE-RESALE", release_status=ON_HOLD)

    with app.app_context():
        job_id = job_by_order("CL-RELEASE-RESALE")["id"]

    post_job_action(client, job_id, "request_resale")
    post_job_action(client, job_id, "release")

    with app.app_context():
        job = get_job(job_id)
        assert job["release_status"] == RELEASED
        assert job["resale_status"] == RESALE_REQUESTED


def test_needs_resale_page_only_shows_active_requested_jobs(app, client):
    login(client, WAREHOUSE, PASSWORDS[WAREHOUSE])
    create_job_via_form(client, "CL-NEEDS-YES")
    create_job_via_form(client, "CL-NEEDS-NO")
    create_job_via_form(client, "CL-NEEDS-COMPLETED")

    with app.app_context():
        requested_id = job_by_order("CL-NEEDS-YES")["id"]
        completed_id = job_by_order("CL-NEEDS-COMPLETED")["id"]

    post_job_action(client, requested_id, "request_resale")
    post_job_action(client, completed_id, "request_resale")

    with app.app_context():
        mark_completed(get_job(completed_id), "warehouse")

    response = client.get("/resale-needed")
    assert b"CL-NEEDS-YES" in response.data
    assert b"CL-NEEDS-NO" not in response.data
    assert b"CL-NEEDS-COMPLETED" not in response.data


def test_resale_request_details_do_not_appear_on_tv_display(app, client):
    login(client, WAREHOUSE, PASSWORDS[WAREHOUSE])
    create_job_via_form(client, "CL-TV-RESALE")

    with app.app_context():
        job_id = job_by_order("CL-TV-RESALE")["id"]

    post_job_action(client, job_id, "request_resale")
    response = client.get("/tv")
    assert b"CL-TV-RESALE" in response.data
    assert b"Resale" not in response.data
    assert b"Requested" not in response.data


def test_resale_status_changes_are_audited(app, client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    create_job_via_form(client, "CL-RESALE-AUDIT")

    with app.app_context():
        job_id = job_by_order("CL-RESALE-AUDIT")["id"]

    post_job_action(client, job_id, "request_resale")
    post_job_action(client, job_id, "provide_resale")
    post_job_action(client, job_id, "reopen_resale")
    post_job_action(client, job_id, "cancel_resale")

    with app.app_context():
        entries = get_db().execute(
            """
            SELECT old_value, new_value, note
            FROM audit_log
            WHERE order_number = ? AND field_changed = ?
            ORDER BY id
            """,
            ("CL-RESALE-AUDIT", "resale_status"),
        ).fetchall()
        notes = [entry["note"] for entry in entries]
        assert "Resale numbers requested" in notes
        assert "Resale numbers provided" in notes
        assert "Resale request reopened" in notes
        assert "Resale request cancelled" in notes
