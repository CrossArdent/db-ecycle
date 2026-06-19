from datetime import date, datetime, timedelta, timezone

from helpers import (
    calculate_days_open,
    calculate_days_since_released,
    calculate_days_since_resale_requested,
    get_aging_level,
)
from models import DEFAULT_USERS, create_job, get_db, get_job, mark_completed
from tests.conftest import login, logout, post_job_action


PASSWORDS = {user["username"]: user["password"] for user in DEFAULT_USERS}
ADMIN = "andy.admin"
ACCOUNT = "account.demo"
WAREHOUSE = "warehouse.manager"
DISPLAY = "warehouse.tv"


def create_direct_job(order_number, release_status="Released", resale_status="Not Needed", date_received=None):
    return create_job(
        {
            "order_number": order_number,
            "customer_name": "Attention Test Customer",
            "date_received": date_received or date.today().isoformat(),
            "release_status": release_status,
            "resale_status": resale_status,
            "notes": "Attention test",
        },
        "admin",
    )


def test_needs_attention_page_visible_to_internal_roles(client):
    for username in [ADMIN, ACCOUNT, WAREHOUSE]:
        response = login(client, username, PASSWORDS[username])
        assert response.status_code == 200
        response = client.get("/needs-attention")
        assert response.status_code == 200
        assert b"Needs Attention" in response.data
        logout(client)


def test_needs_attention_page_blocks_display(client):
    login(client, DISPLAY, PASSWORDS[DISPLAY])
    response = client.get("/needs-attention")
    assert response.status_code == 403


def test_on_hold_and_resale_requested_jobs_appear_once_with_multiple_reasons(app, client):
    today = date.today()
    old_received = (today - timedelta(days=7)).isoformat()
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=6)).replace(microsecond=0).isoformat()

    with app.app_context():
        job_id = create_direct_job("CL-ATTN-MULTI", release_status="On Hold", resale_status="Requested", date_received=old_received)
        get_db().execute(
            """
            UPDATE jobs
            SET resale_requested_at = ?, resale_requested_by = ?, hold_started_at = ?, hold_started_by = ?
            WHERE id = ?
            """,
            (old_timestamp, "account", old_timestamp, "account", job_id),
        )
        get_db().commit()

    login(client, ADMIN, PASSWORDS[ADMIN])
    response = client.get("/needs-attention")
    assert response.data.count(b"CL-ATTN-MULTI") == 1
    assert b"Waiting for Release" in response.data
    assert b"Resale Numbers Needed" in response.data
    assert b"Active Over 5 Days" in response.data
    assert b"Resale Request Over 3 Days" in response.data
    assert b"Long Hold" in response.data


def test_completed_jobs_do_not_appear_in_needs_attention(app, client):
    with app.app_context():
        job_id = create_direct_job("CL-ATTN-COMPLETE", release_status="On Hold")
        mark_completed(get_job(job_id), "warehouse")

    login(client, ADMIN, PASSWORDS[ADMIN])
    response = client.get("/needs-attention")
    assert b"CL-ATTN-COMPLETE" not in response.data


def test_released_too_long_appears_in_needs_attention(app, client):
    old_released_at = (datetime.now(timezone.utc) - timedelta(days=3)).replace(microsecond=0).isoformat()

    with app.app_context():
        job_id = create_direct_job("CL-ATTN-RELEASED")
        get_db().execute(
            "UPDATE jobs SET released_at = ?, released_by = ? WHERE id = ?",
            (old_released_at, "account", job_id),
        )
        get_db().commit()

    login(client, WAREHOUSE, PASSWORDS[WAREHOUSE])
    response = client.get("/needs-attention")
    assert b"CL-ATTN-RELEASED" in response.data
    assert b"Released, Not Completed" in response.data


def test_aging_helpers_calculate_expected_values():
    today = date(2026, 6, 19)
    job = {
        "date_received": "2026-06-10",
        "job_status": "Active",
        "completed_at": None,
        "release_status": "Released",
        "released_at": "2026-06-17T12:00:00+00:00",
        "resale_status": "Requested",
        "resale_requested_at": "2026-06-16T12:00:00+00:00",
    }

    assert calculate_days_open(job, today=today) == 9
    assert calculate_days_since_released(job, today=today) == 2
    assert calculate_days_since_resale_requested(job, today=today) == 3


def test_aging_levels_return_expected_thresholds():
    assert get_aging_level(2, "days_open") == "normal"
    assert get_aging_level(3, "days_open") == "warning"
    assert get_aging_level(6, "days_open") == "urgent"
    assert get_aging_level(1, "days_since_released") == "normal"
    assert get_aging_level(2, "days_since_released") == "warning"
    assert get_aging_level(4, "days_since_released") == "urgent"
    assert get_aging_level(1, "days_since_resale_requested") == "normal"
    assert get_aging_level(2, "days_since_resale_requested") == "warning"
    assert get_aging_level(4, "days_since_resale_requested") == "urgent"


def test_status_badges_render_on_internal_pages(app, client):
    with app.app_context():
        active_id = create_direct_job("CL-BADGE-ACTIVE", resale_status="Requested")
        completed_id = create_direct_job("CL-BADGE-COMPLETE")
        mark_completed(get_job(completed_id), "warehouse")
        get_db().execute(
            "UPDATE jobs SET resale_requested_at = ?, resale_requested_by = ? WHERE id = ?",
            (datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "account", active_id),
        )
        get_db().commit()

    login(client, ADMIN, PASSWORDS[ADMIN])
    active = client.get("/jobs")
    completed = client.get("/completed")
    attention = client.get("/needs-attention")

    assert b"badge-released" in active.data
    assert b"badge-active" in active.data
    assert b"badge-resale-requested" in active.data
    assert b"badge-completed" in completed.data
    assert b"badge-attention" in attention.data


def test_confirmation_prompts_exist_on_action_buttons(app, client):
    with app.app_context():
        job_id = create_direct_job("CL-CONFIRM", release_status="On Hold", resale_status="Requested")
        hold_job_id = create_direct_job("CL-CONFIRM-HOLD")
        reopen_job_id = create_direct_job("CL-CONFIRM-REOPEN")
        mark_completed(get_job(reopen_job_id), "warehouse")

    login(client, ADMIN, PASSWORDS[ADMIN])
    response = client.get(f"/jobs/{job_id}/edit")
    expected_prompts = [
        b"Are you sure you want to release this job?",
        b"Are you sure you want to mark this job completed?",
        b"Are you sure you want to cancel this resale numbers request?",
        b"Are you sure you want to mark resale numbers as provided?",
        b"Are you sure you want to delete this job?",
    ]
    for prompt in expected_prompts:
        assert prompt in response.data

    response = client.get(f"/jobs/{hold_job_id}/edit")
    assert b"Are you sure you want to place this job on hold?" in response.data

    response = client.get(f"/jobs/{reopen_job_id}/edit")
    assert b"Are you sure you want to reopen this completed job?" in response.data

    post_job_action(client, job_id, "provide_resale")
    response = client.get(f"/jobs/{job_id}/edit")
    assert b"Are you sure you want to reopen this resale numbers request?" in response.data
