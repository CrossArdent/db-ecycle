from models import DEFAULT_USERS, get_db, get_job, get_user_by_username, seed_default_users
from tests.conftest import create_job_via_form, csrf_token, login, logout, post_job_action


PASSWORDS = {user["username"]: user["password"] for user in DEFAULT_USERS}
ADMIN = "andy.admin"
ACCOUNT = "account.demo"
WAREHOUSE = "warehouse.manager"
DISPLAY = "warehouse.tv"


def job_by_order(order_number):
    return get_db().execute("SELECT * FROM jobs WHERE order_number = ?", (order_number,)).fetchone()


def create_named_user(client, username="maria.account", role="Account Manager", password="temp-pass-1"):
    response = client.get("/users/new")
    token = csrf_token(response)
    return client.post(
        "/users/new",
        data={
            "csrf_token": token,
            "username": username,
            "full_name": "Maria Jones",
            "email": "maria@example.local",
            "role": role,
            "active": "1",
            "password": password,
        },
        follow_redirects=True,
    )


def reset_password(client, user_id, password):
    response = client.get(f"/users/{user_id}/edit")
    token = csrf_token(response)
    return client.post(
        f"/users/{user_id}/reset-password",
        data={"csrf_token": token, "password": password},
        follow_redirects=True,
    )


def set_active(client, user_id, active):
    response = client.get("/users")
    token = csrf_token(response)
    return client.post(
        f"/users/{user_id}/set-active",
        data={"csrf_token": token, "active": "1" if active else "0"},
        follow_redirects=True,
    )


def test_users_page_access_is_admin_only(client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    assert client.get("/users").status_code == 200
    logout(client)

    for username in [ACCOUNT, WAREHOUSE, DISPLAY]:
        login(client, username, PASSWORDS[username])
        assert client.get("/users").status_code == 403
        logout(client)


def test_admin_can_create_named_user_assign_role_and_user_can_login(app, client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    response = create_named_user(client, role="Warehouse Manager")
    assert b"User created" in response.data

    with app.app_context():
        user = get_user_by_username("maria.account")
        assert user is not None
        assert user["full_name"] == "Maria Jones"
        assert user["role"] == "Warehouse Manager"
        assert user["active"] == 1
        assert user["password_hash"] != "temp-pass-1"

    logout(client)
    response = login(client, "maria.account", "temp-pass-1")
    assert response.status_code == 200
    assert b"Active Jobs" in response.data


def test_admin_can_deactivate_user_and_inactive_user_cannot_log_in(app, client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    create_named_user(client, username="inactive.user")

    with app.app_context():
        user_id = get_user_by_username("inactive.user")["id"]

    response = set_active(client, user_id, False)
    assert b"User deactivated" in response.data

    logout(client)
    response = login(client, "inactive.user", "temp-pass-1")
    assert b"Invalid username or password" in response.data


def test_admin_can_reset_user_password(app, client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    create_named_user(client, username="reset.user")

    with app.app_context():
        user_id = get_user_by_username("reset.user")["id"]

    response = reset_password(client, user_id, "new-temp-pass")
    assert b"Password reset" in response.data

    logout(client)
    assert b"Invalid username or password" in login(client, "reset.user", "temp-pass-1").data
    response = login(client, "reset.user", "new-temp-pass")
    assert b"Active Jobs" in response.data


def test_named_user_permissions_are_based_on_role(app, client):
    login(client, ADMIN, PASSWORDS[ADMIN])
    create_named_user(client, username="role.account", role="Account Manager", password="role-pass")
    logout(client)

    login(client, "role.account", "role-pass")
    create_job_via_form(client, "CL-NAMED-ROLE", release_status="On Hold")

    with app.app_context():
        job_id = job_by_order("CL-NAMED-ROLE")["id"]

    response = post_job_action(client, job_id, "release")
    assert b"Job released" in response.data

    with app.app_context():
        job = get_job(job_id)
        assert job["released_by"] == "Maria Jones"
        assert job["completed_by"] == "Maria Jones"


def test_audit_logs_show_individual_named_users(app, client):
    login(client, ACCOUNT, PASSWORDS[ACCOUNT])
    create_job_via_form(client, "CL-NAMED-AUDIT", release_status="On Hold")

    with app.app_context():
        job_id = job_by_order("CL-NAMED-AUDIT")["id"]

    post_job_action(client, job_id, "release")

    with app.app_context():
        entry = get_db().execute(
            """
            SELECT username FROM audit_log
            WHERE order_number = ? AND field_changed = ?
            ORDER BY id DESC
            """,
            ("CL-NAMED-AUDIT", "release_status"),
        ).fetchone()
        assert entry["username"] == "Demo Account Manager"


def test_old_audit_log_values_still_display(client, app):
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO audit_log
                (timestamp, job_id, order_number, username, field_changed, old_value, new_value, note)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-06-19T12:00:00+00:00", "OLD-1", "account", "legacy", "old", "new", "Legacy entry"),
        )
        get_db().commit()

    login(client, ADMIN, PASSWORDS[ADMIN])
    response = client.get("/audit-log")
    assert b"account" in response.data
    assert b"Legacy entry" in response.data


def test_seed_users_is_idempotent(app):
    with app.app_context():
        before = get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
        seed_default_users()
        seed_default_users()
        after = get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert after == before


def test_password_hashes_are_not_plaintext(app):
    with app.app_context():
        for user in DEFAULT_USERS:
            row = get_user_by_username(user["username"])
            assert row["password_hash"] != user["password"]
            assert user["password"] not in row["password_hash"]
