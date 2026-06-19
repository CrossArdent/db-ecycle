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

- `admin / P@55w0rd`
- `account / Brett`
- `warehouse / Scott`
- `display / display`

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

## Docker Deployment

For an Ubuntu server deployment in `/opt/warehouse-dashboard`:

```bash
cd /opt/warehouse-dashboard
cp .env.example .env
mkdir -p instance
docker compose up -d --build
docker compose exec warehouse-dashboard python scripts/migrate_db.py
```

To update an existing Docker deployment:

```bash
cd /opt/warehouse-dashboard
cp instance/warehouse_dashboard.sqlite3 instance/warehouse_dashboard_$(date +%Y%m%d_%H%M%S).sqlite3
git pull origin main
docker compose up -d --build
docker compose exec warehouse-dashboard python scripts/migrate_db.py
docker compose logs --tail=50 warehouse-dashboard
```

The compose file publishes the dashboard on port 80 and mounts `./instance` into the container, so the SQLite database remains on the mini PC across image rebuilds.

To reset the local users to the credentials documented above, run:

```bash
docker compose exec warehouse-dashboard python scripts/seed_users.py
```

This updates the password hashes for the default users without storing plaintext passwords in SQLite.

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

## Needs Attention

Use `http://127.0.0.1:5000/needs-attention` for the internal Needs Attention page. It is visible to Admin, Account Manager, and Warehouse Manager users. Warehouse Display users cannot access it.

Needs Attention is calculated from active jobs and can show multiple reasons on one job:

- `Waiting for Release`
- `Resale Numbers Needed`
- `Released, Not Completed`
- `Active Over 5 Days`
- `Resale Request Over 3 Days`
- `Long Hold`

The warehouse TV page remains focused on physical warehouse action and does not show resale-specific queues.

## Aging Indicators

Internal pages show calculated aging indicators:

- Days Open
- Days On Hold
- Days Since Released
- Days Since Resale Requested

Aging badges use these levels:

- Normal
- Warning
- Urgent

The TV display stays uncluttered and only shows Days Open for released active jobs and Days On Hold for held jobs.

## Status Badges

Release, job, resale, attention, and aging statuses are shown with text badges. Color is used as a visual aid, but the badge text remains visible for accessibility.

## Confirmation Prompts

Important workflow actions use browser confirmation prompts, including release, hold, complete, reopen, resale status changes, and delete. Permissions are still enforced server-side.

## Resale Numbers Workflow

Resale Status is separate from Release Status. Release Status still controls whether the warehouse may process an order. Resale Status only tracks whether resale numbers are needed.

Resale Status values:

- `Not Needed`
- `Requested`
- `Provided`

New jobs default to `Not Needed`. Account Managers and Warehouse Managers can request resale numbers. Account Managers can cancel a request, Warehouse Managers can mark numbers provided, and Admins can do all resale actions including reopening a provided request.

Use `http://127.0.0.1:5000/resale-needed` for the Needs Resale Numbers queue. The warehouse TV page does not show resale request details in version 1.

## Current Release Workflow

When a job is changed from `On Hold` to `Released`, the app records the release, sends the warehouse notification if SMTP is configured, and automatically moves the job to `Completed`.

## Database

SQLite is stored by default at:

```text
instance/warehouse_dashboard.sqlite3
```

Override it with `DATABASE_PATH` in `.env`.

To apply safe schema updates after pulling or copying a new version, run:

```powershell
python scripts/migrate_db.py
```

For Docker-based deployments, use:

```powershell
docker compose exec warehouse-dashboard python scripts/migrate_db.py
```

Back up the database by stopping the app briefly or ensuring no writes are happening, then copying the SQLite file:

```powershell
Copy-Item instance\warehouse_dashboard.sqlite3 backups\warehouse_dashboard_YYYYMMDD.sqlite3
```

## Tests

```powershell
pytest
```

The test suite covers login, default statuses, duplicate order rejection, role permissions, display restrictions, TV display filtering, audit logging, and release behavior when SMTP is not configured.
