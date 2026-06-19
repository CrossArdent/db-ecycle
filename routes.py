import sqlite3
from datetime import date, datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from auth import (
    admin_required,
    can_complete_job,
    can_create_job,
    can_delete_job,
    can_cancel_resale,
    can_hold_job,
    can_provide_resale,
    can_release_job,
    can_reopen_job,
    can_reopen_resale,
    can_request_resale,
    current_user,
    editable_fields_for,
    login_required,
    non_display_required,
    require_csrf,
)
from models import (
    ACTIVE,
    COMPLETED,
    ON_HOLD,
    RELEASED,
    RESALE_NOT_NEEDED,
    RESALE_PROVIDED,
    RESALE_REQUESTED,
    authenticate_user,
    change_release_status,
    change_resale_status,
    create_job,
    delete_job,
    get_active_jobs,
    get_audit_entries,
    get_completed_jobs,
    get_job,
    get_resale_needed_jobs,
    get_tv_jobs,
    mark_completed,
    parse_timestamp,
    reopen_job,
    update_job_fields,
)
from notifications import send_release_email


bp = Blueprint("main", __name__)


def days_open(job):
    received = date.fromisoformat(job["date_received"])
    end = date.today()
    if job["completed_at"]:
        end = parse_timestamp(job["completed_at"]).date()
    return (end - received).days


@bp.app_template_filter("days_open")
def days_open_filter(job):
    return days_open(job)


@bp.app_template_filter("short_dt")
def short_dt(value):
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@bp.route("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("main.login"))
    if user["role"] == "Warehouse Display":
        return redirect(url_for("main.tv"))
    return redirect(url_for("main.active_jobs"))


@bp.route("/login", methods=["GET", "POST"])
@require_csrf
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = authenticate_user(username, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = request.form.get("csrf_token")
            flash("Logged in successfully.", "success")
            if user["role"] == "Warehouse Display":
                return redirect(url_for("main.tv"))
            return redirect(request.args.get("next") or url_for("main.active_jobs"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("main.login"))


@bp.route("/jobs")
@login_required
def active_jobs():
    user = current_user()
    if user["role"] == "Warehouse Display":
        return redirect(url_for("main.tv"))
    release_filter = request.args.get("release_status")
    order_number = request.args.get("order_number", "")
    customer_name = request.args.get("customer_name", "")
    jobs = get_active_jobs(release_filter, order_number, customer_name)
    return render_template(
        "active_jobs.html",
        jobs=jobs,
        release_filter=release_filter,
        order_number=order_number,
        customer_name=customer_name,
    )


@bp.route("/completed")
@login_required
def completed_jobs():
    user = current_user()
    if user["role"] == "Warehouse Display":
        return redirect(url_for("main.tv"))
    return render_template("completed_jobs.html", jobs=get_completed_jobs())


@bp.route("/resale-needed")
@login_required
def resale_needed():
    user = current_user()
    if user["role"] == "Warehouse Display":
        abort(403)
    return render_template("resale_needed.html", jobs=get_resale_needed_jobs())


@bp.route("/jobs/new", methods=["GET", "POST"])
@non_display_required
@require_csrf
def new_job():
    user = current_user()
    if not can_create_job(user):
        abort(403)
    if request.method == "POST":
        data = {
            "order_number": request.form.get("order_number", ""),
            "customer_name": request.form.get("customer_name", ""),
            "date_received": request.form.get("date_received", ""),
            "release_status": request.form.get("release_status", RELEASED),
            "resale_status": RESALE_NOT_NEEDED,
            "notes": request.form.get("notes", ""),
        }
        errors = validate_job_form(data)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                job_id = create_job(data, user["username"])
                flash("Job created.", "success")
                return redirect(url_for("main.edit_job", job_id=job_id))
            except sqlite3.IntegrityError:
                flash("Order number already exists.", "error")
    else:
        data = {
            "order_number": "",
            "customer_name": "",
            "date_received": date.today().isoformat(),
            "release_status": RELEASED,
            "resale_status": RESALE_NOT_NEEDED,
            "notes": "",
        }
    return render_template("job_form.html", data=data, mode="new")


@bp.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
@non_display_required
@require_csrf
def edit_job(job_id):
    user = current_user()
    job = get_job(job_id)
    if not job:
        abort(404)

    fields = editable_fields_for(user)
    if request.method == "POST":
        data = {field: request.form.get(field, "") for field in fields}
        if "release_status" in data and job["release_status"] == ON_HOLD and data["release_status"] == RELEASED:
            if not can_release_job(user):
                flash("Warehouse Managers cannot release held jobs. Ask an Admin or Account Manager to release this order.", "error")
                return redirect(url_for("main.edit_job", job_id=job_id))
        errors = validate_edit_form(data, fields)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                release_status = data.pop("release_status", None)
                job_status = data.pop("job_status", None)
                update_job_fields(job, data, user["username"], [field for field in fields if field not in {"release_status", "job_status"}])

                job = get_job(job_id)
                completes_on_release = job["release_status"] == ON_HOLD and release_status == RELEASED
                if release_status and release_status != job["release_status"]:
                    changed = change_release_status(job, release_status, user["username"])
                    if changed and release_status == RELEASED:
                        released_job = get_job(job_id)
                        sent, message = send_release_email(released_job, user["username"], released_job["released_at"])
                        if not sent:
                            flash(message, "warning")

                job = get_job(job_id)
                if job_status and not completes_on_release and job_status != job["job_status"]:
                    if job_status == COMPLETED:
                        mark_completed(job, user["username"])
                    elif job_status == ACTIVE:
                        reopen_job(job, user["username"])

                flash("Job updated.", "success")
                return redirect(url_for("main.edit_job", job_id=job_id))
            except sqlite3.IntegrityError:
                flash("Order number already exists.", "error")
            except ValueError as exc:
                flash(str(exc), "error")

    return render_template("edit_job.html", job=job, fields=fields)


@bp.route("/jobs/<int:job_id>/action", methods=["POST"])
@non_display_required
@require_csrf
def job_action(job_id):
    user = current_user()
    job = get_job(job_id)
    if not job:
        abort(404)

    action = request.form.get("action")
    if action == "hold":
        if not can_hold_job(user):
            abort(403)
        change_release_status(job, ON_HOLD, user["username"])
        flash("Job marked On Hold.", "success")
    elif action == "release":
        if not can_release_job(user):
            flash("Warehouse Managers cannot release held jobs. Ask an Admin or Account Manager to release this order.", "error")
            return redirect(url_for("main.edit_job", job_id=job_id))
        changed = change_release_status(job, RELEASED, user["username"])
        if changed:
            released_job = get_job(job_id)
            sent, message = send_release_email(released_job, user["username"], released_job["released_at"])
            flash("Job released." if sent else f"Job released. {message}", "success" if sent else "warning")
        else:
            flash("Job is already released.", "success")
    elif action == "complete":
        if not can_complete_job(user):
            flash("Only Admins and Warehouse Managers can mark jobs completed.", "error")
            return redirect(url_for("main.edit_job", job_id=job_id))
        mark_completed(job, user["username"])
        flash("Job marked completed.", "success")
    elif action == "reopen":
        if not can_reopen_job(user):
            abort(403)
        reopen_job(job, user["username"])
        flash("Job reopened.", "success")
    elif action == "delete":
        if not can_delete_job(user):
            abort(403)
        delete_job(job, user["username"])
        flash(f"Job {job['order_number']} deleted.", "success")
        return redirect(url_for("main.active_jobs"))
    elif action == "request_resale":
        if not can_request_resale(user) or job["resale_status"] != RESALE_NOT_NEEDED:
            abort(403)
        change_resale_status(job, RESALE_REQUESTED, user["username"], "Resale numbers requested")
        flash("Resale numbers requested.", "success")
    elif action == "cancel_resale":
        if not can_cancel_resale(user) or job["resale_status"] != RESALE_REQUESTED:
            abort(403)
        change_resale_status(job, RESALE_NOT_NEEDED, user["username"], "Resale request cancelled")
        flash("Resale request cancelled.", "success")
    elif action == "provide_resale":
        if not can_provide_resale(user) or job["resale_status"] != RESALE_REQUESTED:
            abort(403)
        change_resale_status(job, RESALE_PROVIDED, user["username"], "Resale numbers provided")
        flash("Resale numbers marked provided.", "success")
    elif action == "reopen_resale":
        if not can_reopen_resale(user) or job["resale_status"] != RESALE_PROVIDED:
            abort(403)
        change_resale_status(job, RESALE_REQUESTED, user["username"], "Resale request reopened")
        flash("Resale request reopened.", "success")
    else:
        abort(400)
    return redirect(url_for("main.edit_job", job_id=job_id))


@bp.route("/tv")
@login_required
def tv():
    released, held, completed = get_tv_jobs()
    now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    return render_template("tv.html", released=released, held=held, completed=completed, now=now)


@bp.route("/audit-log")
@admin_required
def audit_log():
    return render_template("audit_log.html", entries=get_audit_entries())


def validate_job_form(data):
    errors = []
    if not data.get("order_number", "").strip():
        errors.append("Order Number is required.")
    if not data.get("customer_name", "").strip():
        errors.append("Customer Name is required.")
    if not data.get("date_received", ""):
        errors.append("Date Received is required.")
    else:
        try:
            date.fromisoformat(data["date_received"])
        except ValueError:
            errors.append("Date Received must be a valid date.")
    if data.get("release_status") not in {RELEASED, ON_HOLD}:
        errors.append("Release Status is invalid.")
    return errors


def validate_edit_form(data, fields):
    errors = []
    required = {"order_number": "Order Number", "customer_name": "Customer Name", "date_received": "Date Received"}
    for field, label in required.items():
        if field in fields and not data.get(field, "").strip():
            errors.append(f"{label} is required.")
    if "date_received" in fields and data.get("date_received"):
        try:
            date.fromisoformat(data["date_received"])
        except ValueError:
            errors.append("Date Received must be a valid date.")
    if "release_status" in fields and data.get("release_status") not in {RELEASED, ON_HOLD}:
        errors.append("Release Status is invalid.")
    if "job_status" in fields and data.get("job_status") not in {ACTIVE, COMPLETED}:
        errors.append("Job Status is invalid.")
    return errors
