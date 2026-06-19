from models import DEFAULT_USERS, ON_HOLD, RELEASED, get_db, get_job
from tests.conftest import create_job_via_form, login, logout, post_job_action


PASSWORDS = {username: password for username, password, role in DEFAULT_USERS}


def job_by_order(order_number):
    return get_db().execute("SELECT * FROM jobs WHERE order_number = ?", (order_number,)).fetchone()


def test_all_default_users_can_log_in(client):
    users = [
        ("admin", PASSWORDS["admin"], b"Active Jobs"),
        ("account", PASSWORDS["account"], b"Active Jobs"),
        ("warehouse", PASSWORDS["warehouse"], b"Active Jobs"),
        ("display", PASSWORDS["display"], b"Warehouse Orders"),
    ]
    for username, password, expected in users:
        response = login(client, username, password)
        assert response.status_code == 200
        assert expected in response.data
        logout(client)


def test_account_manager_can_create_job_with_defaults_and_duplicate_is_rejected(app, client):
    login(client, "account", PASSWORDS["account"])

    response = create_job_via_form(client, "CL-DUP-1")
    assert response.status_code == 200
    assert b"Job created" in response.data

    with app.app_context():
        job = job_by_order("CL-DUP-1")
        assert job["release_status"] == RELEASED
        assert job["job_status"] == "Active"

    response = create_job_via_form(client, "CL-DUP-1")
    assert b"Order number already exists" in response.data


def test_warehouse_manager_cannot_release_on_hold_job_server_side(app, client):
    login(client, "account", PASSWORDS["account"])
    create_job_via_form(client, "CL-HOLD-1", release_status=ON_HOLD)
    logout(client)

    with app.app_context():
        job_id = job_by_order("CL-HOLD-1")["id"]

    login(client, "warehouse", PASSWORDS["warehouse"])
    response = post_job_action(client, job_id, "release")
    assert b"Warehouse Managers cannot release held jobs" in response.data

    with app.app_context():
        assert get_job(job_id)["release_status"] == ON_HOLD


def test_account_manager_can_release_on_hold_job_and_missing_smtp_does_not_block(app, client):
    login(client, "account", PASSWORDS["account"])
    create_job_via_form(client, "CL-REL-1", release_status=ON_HOLD)

    with app.app_context():
        job_id = job_by_order("CL-REL-1")["id"]

    response = post_job_action(client, job_id, "release")
    assert b"Job released" in response.data
    assert b"Email not sent because SMTP settings are missing" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["release_status"] == RELEASED
        assert job["job_status"] == "Completed"
        assert job["released_by"] == "account"
        assert job["completed_by"] == "account"
        audit_count = get_db().execute(
            "SELECT COUNT(*) FROM audit_log WHERE order_number = ? AND field_changed = ?",
            ("CL-REL-1", "release_status"),
        ).fetchone()[0]
        assert audit_count == 1
        status_audit_count = get_db().execute(
            "SELECT COUNT(*) FROM audit_log WHERE order_number = ? AND field_changed = ? AND new_value = ?",
            ("CL-REL-1", "job_status", "Completed"),
        ).fetchone()[0]
        assert status_audit_count == 1


def test_warehouse_manager_can_complete_but_account_manager_cannot(app, client):
    login(client, "warehouse", PASSWORDS["warehouse"])
    create_job_via_form(client, "CL-COMPLETE-1")

    with app.app_context():
        warehouse_job_id = job_by_order("CL-COMPLETE-1")["id"]

    response = post_job_action(client, warehouse_job_id, "complete")
    assert b"Job marked completed" in response.data

    with app.app_context():
        assert get_job(warehouse_job_id)["job_status"] == "Completed"

    logout(client)
    login(client, "account", PASSWORDS["account"])
    create_job_via_form(client, "CL-COMPLETE-2")

    with app.app_context():
        account_job_id = job_by_order("CL-COMPLETE-2")["id"]

    response = post_job_action(client, account_job_id, "complete")
    assert b"Only Admins and Warehouse Managers can mark jobs completed" in response.data

    with app.app_context():
        assert get_job(account_job_id)["job_status"] == "Active"


def test_admin_can_reopen_completed_job(app, client):
    login(client, "warehouse", PASSWORDS["warehouse"])
    create_job_via_form(client, "CL-REOPEN-1")

    with app.app_context():
        job_id = job_by_order("CL-REOPEN-1")["id"]

    post_job_action(client, job_id, "complete")
    logout(client)

    login(client, "admin", PASSWORDS["admin"])
    response = post_job_action(client, job_id, "reopen")
    assert b"Job reopened" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["job_status"] == "Active"
        assert job["completed_at"] is None


def test_marking_completed_job_on_hold_returns_it_to_active(app, client):
    login(client, "warehouse", PASSWORDS["warehouse"])
    create_job_via_form(client, "CL-HOLD-REOPEN")

    with app.app_context():
        job_id = job_by_order("CL-HOLD-REOPEN")["id"]

    post_job_action(client, job_id, "complete")
    response = post_job_action(client, job_id, "hold")
    assert b"Job marked On Hold" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["release_status"] == ON_HOLD
        assert job["job_status"] == "Active"
        assert job["completed_at"] is None
        assert job["completed_by"] is None
        status_audit_count = get_db().execute(
            "SELECT COUNT(*) FROM audit_log WHERE order_number = ? AND field_changed = ? AND new_value = ?",
            ("CL-HOLD-REOPEN", "job_status", "Active"),
        ).fetchone()[0]
        assert status_audit_count == 1


def test_admin_can_delete_job_and_audit_entry_remains(app, client):
    login(client, "admin", PASSWORDS["admin"])
    create_job_via_form(client, "CL-DELETE-1")

    with app.app_context():
        job_id = job_by_order("CL-DELETE-1")["id"]

    response = post_job_action(client, job_id, "delete")
    assert b"Job CL-DELETE-1 deleted" in response.data

    with app.app_context():
        assert get_job(job_id) is None
        audit_entry = get_db().execute(
            """
            SELECT * FROM audit_log
            WHERE order_number = ? AND field_changed = ? AND new_value = ?
            """,
            ("CL-DELETE-1", "job", "deleted"),
        ).fetchone()
        assert audit_entry is not None
        assert audit_entry["username"] == "admin"


def test_non_admin_cannot_delete_job_server_side(app, client):
    login(client, "admin", PASSWORDS["admin"])
    create_job_via_form(client, "CL-DELETE-BLOCKED")

    with app.app_context():
        job_id = job_by_order("CL-DELETE-BLOCKED")["id"]

    logout(client)
    login(client, "warehouse", PASSWORDS["warehouse"])
    response = post_job_action(client, job_id, "delete")
    assert response.status_code == 403

    with app.app_context():
        assert get_job(job_id) is not None
