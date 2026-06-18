# Warehouse Order Dashboard

A production-minded, LAN-only Flask dashboard for manually tracking warehouse orders from CycleLution order numbers. Version 1 is intentionally local and simple: Python, Flask, SQLite, Jinja templates, role-based login, a read-only TV display, audit logging, and SMTP email notification when a held job is released.

## Version 1 Scope

- Manual order entry only.
- No CycleLution integration.
- No Google Workspace, Microsoft 365, Slack, or Teams integrations.
- No advanced reporting.
- No Excel export.
- No remote access features.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and change `SECRET_KEY`.

```powershell
Copy-Item .env.example .env
```

## Initialize and Seed

```powershell
python scripts/init_db.py
python scripts/seed_users.py
python scripts/seed_sample_jobs.py
```

Default local test users are defined in `scripts/seed_users.py` and `models.py`:

- `admin / change-me-admin`
- `account / change-me-account`
- `warehouse / change-me-warehouse`
- `display / change-me-display`

To change users or passwords, edit the default list in `models.py` or `scripts/seed_users.py`, then rerun:

```powershell
python scripts/seed_users.py
```

The seed command updates existing users with the configured password and role.

## Run Locally

```powershell
python app.py
```

Default URLs:

- App login: `http://127.0.0.1:5000/login`
- Active jobs: `http://127.0.0.1:5000/jobs`
- Completed jobs: `http://127.0.0.1:5000/completed`
- Warehouse TV display: `http://127.0.0.1:5000/tv`
- Admin audit log: `http://127.0.0.1:5000/audit-log`

For LAN use, run on the local interface and allow the port through the machine firewall:

```powershell
python app.py
```

`app.py` binds to `0.0.0.0:5000` when run directly. Other PCs on the same LAN can browse to `http://YOUR_SERVER_IP:5000/login`.

## SMTP Email Notification

Set these in `.env` or as environment variables:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
WAREHOUSE_MANAGER_EMAIL=
```

When an On Hold job is released, the app attempts to email the warehouse manager. If required SMTP settings are missing, the release still succeeds, a warning is logged, and the app shows a warning message.

Do not store real SMTP passwords in source control.

## Roles

- Admin: create jobs, edit all job fields, hold, release, complete, reopen, delete jobs, view audit log.
- Account Manager: create jobs, edit basic job info, hold, release, view jobs.
- Warehouse Manager: create jobs, edit notes, hold, complete jobs, view jobs. Warehouse Managers are blocked server-side from releasing held jobs.
- Warehouse Display: read-only TV dashboard access only.

## Current Release Workflow

When a job is changed from `On Hold` to `Released`, the app records the release, sends the warehouse notification if SMTP is configured, and automatically moves the job to `Completed`.

## Database

SQLite is stored by default at:

```text
instance/warehouse_dashboard.sqlite3
```

Override it with `DATABASE_PATH` in `.env`.

Back up the database by stopping the app briefly or ensuring no writes are happening, then copying the SQLite file:

```powershell
Copy-Item instance\warehouse_dashboard.sqlite3 backups\warehouse_dashboard_YYYYMMDD.sqlite3
```

## Tests

```powershell
pytest
```

The test suite covers login, default statuses, duplicate order rejection, role permissions, display restrictions, TV display filtering, audit logging, and release behavior when SMTP is not configured.
