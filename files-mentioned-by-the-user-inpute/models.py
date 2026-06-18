import sqlite3
from datetime import datetime, timedelta, timezone

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash


ROLE_ADMIN = "Admin"
ROLE_ACCOUNT = "Account Manager"
ROLE_WAREHOUSE = "Warehouse Manager"
ROLE_DISPLAY = "Warehouse Display"

RELEASED = "Released"
ON_HOLD = "On Hold"
ACTIVE = "Active"
COMPLETED = "Completed"

RELEASE_STATUSES = {RELEASED, ON_HOLD}
JOB_STATUSES = {ACTIVE, COMPLETED}

DEFAULT_USERS = [
    ("admin", "change-me-admin", ROLE_ADMIN),
    ("account", "change-me-account", ROLE_ACCOUNT),
    ("warehouse", "change-me-warehouse", ROLE_WAREHOUSE),
    ("display", "change-me-display", ROLE_DISPLAY),
]


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_timestamp(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL,
            date_received TEXT NOT NULL,
            release_status TEXT NOT NULL,
            job_status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            released_at TEXT,
            released_by TEXT,
            completed_at TEXT,
            completed_by TEXT,
            CHECK (release_status IN ('Released', 'On Hold')),
            CHECK (job_status IN ('Active', 'Completed'))
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            job_id INTEGER,
            order_number TEXT,
            username TEXT NOT NULL,
            field_changed TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            note TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
        );
        """
    )
    db.commit()


def create_user(username, password, role):
    if role not in {ROLE_ADMIN, ROLE_ACCOUNT, ROLE_WAREHOUSE, ROLE_DISPLAY}:
        raise ValueError("Invalid role")
    db = get_db()
    db.execute(
        """
        INSERT INTO users (username, password_hash, role, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash = excluded.password_hash,
            role = excluded.role
        """,
        (username, generate_password_hash(password), role, utcnow()),
    )
    db.commit()


def seed_default_users():
    for username, password, role in DEFAULT_USERS:
        create_user(username, password, role)


def get_user_by_username(username):
    return get_db().execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def get_user_by_id(user_id):
    return get_db().execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def audit(job_id, order_number, username, field_changed, old_value, new_value, note):
    get_db().execute(
        """
        INSERT INTO audit_log
            (timestamp, job_id, order_number, username, field_changed, old_value, new_value, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utcnow(),
            job_id,
            order_number,
            username,
            field_changed,
            old_value,
            new_value,
            note,
        ),
    )


def create_job(data, username):
    release_status = data.get("release_status") or RELEASED
    if release_status not in RELEASE_STATUSES:
        raise ValueError("Invalid release status")

    now = utcnow()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO jobs (
            order_number, customer_name, date_received, release_status, job_status, notes,
            created_at, created_by, updated_at, updated_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["order_number"].strip(),
            data["customer_name"].strip(),
            data["date_received"],
            release_status,
            ACTIVE,
            data.get("notes", "").strip(),
            now,
            username,
            now,
            username,
        ),
    )
    job_id = cursor.lastrowid
    audit(job_id, data["order_number"].strip(), username, "job", "", "created", "Job created")
    db.commit()
    return job_id


def get_job(job_id):
    return get_db().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def get_active_jobs(release_status=None, order_number=None, customer_name=None):
    clauses = ["job_status = ?"]
    params = [ACTIVE]
    if release_status in RELEASE_STATUSES:
        clauses.append("release_status = ?")
        params.append(release_status)
    if order_number:
        clauses.append("order_number LIKE ?")
        params.append(f"%{order_number.strip()}%")
    if customer_name:
        clauses.append("customer_name LIKE ?")
        params.append(f"%{customer_name.strip()}%")
    sql = f"""
        SELECT * FROM jobs
        WHERE {' AND '.join(clauses)}
        ORDER BY date_received ASC, updated_at DESC
    """
    return get_db().execute(sql, params).fetchall()


def get_completed_jobs():
    return get_db().execute(
        """
        SELECT * FROM jobs
        WHERE job_status = ?
        ORDER BY completed_at DESC, date_received DESC
        """,
        (COMPLETED,),
    ).fetchall()


def get_tv_jobs():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).replace(microsecond=0).isoformat()
    db = get_db()
    released = db.execute(
        """
        SELECT * FROM jobs
        WHERE job_status = ? AND release_status = ?
        ORDER BY date_received ASC
        """,
        (ACTIVE, RELEASED),
    ).fetchall()
    held = db.execute(
        """
        SELECT * FROM jobs
        WHERE job_status = ? AND release_status = ?
        ORDER BY date_received ASC
        """,
        (ACTIVE, ON_HOLD),
    ).fetchall()
    completed = db.execute(
        """
        SELECT * FROM jobs
        WHERE job_status = ? AND completed_at >= ?
        ORDER BY completed_at DESC
        """,
        (COMPLETED, cutoff),
    ).fetchall()
    return released, held, completed


def get_audit_entries(limit=250):
    return get_db().execute(
        """
        SELECT * FROM audit_log
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def update_job_fields(job, data, username, allowed_fields):
    updates = {}
    for field in allowed_fields:
        if field not in data:
            continue
        value = data[field].strip() if isinstance(data[field], str) else data[field]
        if value != (job[field] or ""):
            updates[field] = value

    if not updates:
        return

    if "release_status" in updates and updates["release_status"] not in RELEASE_STATUSES:
        raise ValueError("Invalid release status")
    if "job_status" in updates and updates["job_status"] not in JOB_STATUSES:
        raise ValueError("Invalid job status")

    now = utcnow()
    assignments = [f"{field} = ?" for field in updates]
    values = list(updates.values())
    assignments.extend(["updated_at = ?", "updated_by = ?"])
    values.extend([now, username, job["id"]])

    db = get_db()
    db.execute(
        f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
        values,
    )
    for field, new_value in updates.items():
        audit(
            job["id"],
            updates.get("order_number", job["order_number"]),
            username,
            field,
            job[field],
            new_value,
            f"{field.replace('_', ' ').title()} changed",
        )
    db.commit()


def change_release_status(job, new_status, username):
    if new_status not in RELEASE_STATUSES:
        raise ValueError("Invalid release status")
    if job["release_status"] == new_status:
        return False

    now = utcnow()
    released_at = now if new_status == RELEASED else job["released_at"]
    released_by = username if new_status == RELEASED else job["released_by"]
    completes_on_release = job["release_status"] == ON_HOLD and new_status == RELEASED
    db = get_db()
    if completes_on_release:
        db.execute(
            """
            UPDATE jobs
            SET release_status = ?, job_status = ?, updated_at = ?, updated_by = ?,
                released_at = ?, released_by = ?, completed_at = ?, completed_by = ?
            WHERE id = ?
            """,
            (new_status, COMPLETED, now, username, released_at, released_by, now, username, job["id"]),
        )
    else:
        db.execute(
            """
            UPDATE jobs
            SET release_status = ?, updated_at = ?, updated_by = ?, released_at = ?, released_by = ?
            WHERE id = ?
            """,
            (new_status, now, username, released_at, released_by, job["id"]),
        )
    audit(
        job["id"],
        job["order_number"],
        username,
        "release_status",
        job["release_status"],
        new_status,
        "Release Status changed",
    )
    if completes_on_release and job["job_status"] != COMPLETED:
        audit(
            job["id"],
            job["order_number"],
            username,
            "job_status",
            job["job_status"],
            COMPLETED,
            "Job completed automatically when released from On Hold",
        )
    db.commit()
    return True


def mark_completed(job, username):
    if job["job_status"] == COMPLETED:
        return False
    now = utcnow()
    db = get_db()
    db.execute(
        """
        UPDATE jobs
        SET job_status = ?, completed_at = ?, completed_by = ?, updated_at = ?, updated_by = ?
        WHERE id = ?
        """,
        (COMPLETED, now, username, now, username, job["id"]),
    )
    audit(
        job["id"],
        job["order_number"],
        username,
        "job_status",
        job["job_status"],
        COMPLETED,
        "Job completed",
    )
    db.commit()
    return True


def reopen_job(job, username):
    if job["job_status"] == ACTIVE:
        return False
    now = utcnow()
    db = get_db()
    db.execute(
        """
        UPDATE jobs
        SET job_status = ?, completed_at = NULL, completed_by = NULL, updated_at = ?, updated_by = ?
        WHERE id = ?
        """,
        (ACTIVE, now, username, job["id"]),
    )
    audit(
        job["id"],
        job["order_number"],
        username,
        "job_status",
        job["job_status"],
        ACTIVE,
        "Job reopened",
    )
    db.commit()
    return True


def delete_job(job, username):
    db = get_db()
    audit(
        job["id"],
        job["order_number"],
        username,
        "job",
        "exists",
        "deleted",
        "Job deleted",
    )
    db.execute("DELETE FROM jobs WHERE id = ?", (job["id"],))
    db.commit()


def seed_sample_jobs():
    user = "admin"
    samples = [
        {
            "order_number": "CL-1001",
            "customer_name": "North Ridge Health",
            "date_received": "2026-06-10",
            "release_status": RELEASED,
            "notes": "Ready for processing.",
        },
        {
            "order_number": "CL-1002",
            "customer_name": "Meridian Schools",
            "date_received": "2026-06-12",
            "release_status": ON_HOLD,
            "notes": "Awaiting customer approval.",
        },
        {
            "order_number": "CL-1003",
            "customer_name": "Summit Finance",
            "date_received": "2026-06-14",
            "release_status": RELEASED,
            "notes": "Sample completed job.",
        },
    ]
    for sample in samples:
        try:
            job_id = create_job(sample, user)
            if sample["order_number"] == "CL-1003":
                mark_completed(get_job(job_id), user)
        except sqlite3.IntegrityError:
            continue
