import sqlite3
from datetime import date, datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from helpers import (
    calculate_days_on_hold,
    calculate_days_open,
    calculate_days_since_released,
    calculate_days_since_resale_requested,
    get_aging_level,
    get_attention_reasons,
    get_suggested_owners,
    job_needs_attention,
)
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
    ROLE_ACCOUNT,
    RESALE_NOT_NEEDED,
    RESALE_PROVIDED,
    RESALE_REQUESTED,
    ROLES,
    authenticate_user,
    change_release_status,
    change_resale_status,
    create_job,
    delete_job,
    display_name_for_user,
    get_active_jobs,
    get_audit_entries,
    get_attention_candidate_jobs,
    get_completed_jobs,
    get_job,
    get_resale_needed_jobs,
    get_tv_jobs,
    get_user_by_id,
    list_users,
    mark_completed,
    parse_timestamp,
    reopen_job,
    set_user_active,
    set_user_password,
    update_user,
    create_user,
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
    return calculate_days_open(job)


@bp.app_template_filter("days_on_hold")
def days_on_hold_filter(job):
    return calculate_days_on_hold(job)


@bp.app_template_filter("days_since_released")
def days_since_released_filter(job):
    return calculate_days_since_released(job)


@bp.app_template_filter("days_since_resale_requested")
def days_since_resale_requested_filter(job):
    return calculate_days_since_resale_requested(job)


@bp.app_template_filter("aging_level")
def aging_level_filter(days, aging_type):
    return get_aging_level(days, aging_type)


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


@bp.route("/needs-attention")
@login_required
def needs_attention():
    user = current_user()
    if user["role"] == "Warehouse Display":
        abort(403)
    rows = []
    for job in get_attention_candidate_jobs():
        reasons = get_attention_reasons(job)
        if reasons:
            rows.append(
                {
                    "job": job,
                    "reasons": reasons,
                    "owners": get_suggested_owners(reasons),
                }
            )
    return render_template("needs_attention.html", rows=rows)


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
    actor = display_name_for_user(user)
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
                job_id = create_job(data, actor)
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
    actor = display_name_for_user(user)
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
                update_job_fields(job, data, actor, [field for field in fields if field not in {"release_status", "job_status"}])

                job = get_job(job_id)
                completes_on_release = job["release_status"] == ON_HOLD and release_status == RELEASED
                if release_status and release_status != job["release_status"]:
                    changed = change_release_status(job, release_status, actor)
                    if changed and release_status == RELEASED:
                        released_job = get_job(job_id)
                        sent, message = send_release_email(released_job, actor, released_job["released_at"])
                        if not sent:
                            flash(message, "warning")

                job = get_job(job_id)
                if job_status and not completes_on_release and job_status != job["job_status"]:
                    if job_status == COMPLETED:
                        mark_completed(job, actor)
                    elif job_status == ACTIVE:
                        reopen_job(job, actor)

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
    actor = display_name_for_user(user)
    job = get_job(job_id)
    if not job:
        abort(404)

    action = request.form.get("action")
    if action == "hold":
        if not can_hold_job(user):
            abort(403)
        change_release_status(job, ON_HOLD, actor)
        flash("Job marked On Hold.", "success")
    elif action == "release":
        if not can_release_job(user):
            flash("Warehouse Managers cannot release held jobs. Ask an Admin or Account Manager to release this order.", "error")
            return redirect(url_for("main.edit_job", job_id=job_id))
        changed = change_release_status(job, RELEASED, actor)
        if changed:
            released_job = get_job(job_id)
            sent, message = send_release_email(released_job, actor, released_job["released_at"])
            flash("Job released." if sent else f"Job released. {message}", "success" if sent else "warning")
        else:
            flash("Job is already released.", "success")
    elif action == "complete":
        if not can_complete_job(user):
            flash("Only Admins and Warehouse Managers can mark jobs completed.", "error")
            return redirect(url_for("main.edit_job", job_id=job_id))
        mark_completed(job, actor)
        flash("Job marked completed.", "success")
    elif action == "reopen":
        if not can_reopen_job(user):
            abort(403)
        reopen_job(job, actor)
        flash("Job reopened.", "success")
    elif action == "delete":
        if not can_delete_job(user):
            abort(403)
        delete_job(job, actor)
        flash(f"Job {job['order_number']} deleted.", "success")
        return redirect(url_for("main.active_jobs"))
    elif action == "request_resale":
        if not can_request_resale(user) or job["resale_status"] != RESALE_NOT_NEEDED:
            abort(403)
        change_resale_status(job, RESALE_REQUESTED, actor, "Resale numbers requested")
        flash("Resale numbers requested.", "success")
    elif action == "cancel_resale":
        if not can_cancel_resale(user) or job["resale_status"] != RESALE_REQUESTED:
            abort(403)
        change_resale_status(job, RESALE_NOT_NEEDED, actor, "Resale request cancelled")
        flash("Resale request cancelled.", "success")
    elif action == "provide_resale":
        if not can_provide_resale(user) or job["resale_status"] != RESALE_REQUESTED:
            abort(403)
        change_resale_status(job, RESALE_PROVIDED, actor, "Resale numbers provided")
        flash("Resale numbers marked provided.", "success")
    elif action == "reopen_resale":
        if not can_reopen_resale(user) or job["resale_status"] != RESALE_PROVIDED:
            abort(403)
        change_resale_status(job, RESALE_REQUESTED, actor, "Resale request reopened")
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


@bp.route("/users")
@admin_required
def users():
    return render_template("users.html", users=list_users(), roles=ROLES)


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
@require_csrf
def new_user():
    data = {
        "username": request.form.get("username", "").strip(),
        "full_name": request.form.get("full_name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "role": request.form.get("role", ROLE_ACCOUNT),
        "active": request.form.get("active", "1") == "1",
    }
    if request.method == "POST":
        password = request.form.get("password", "")
        errors = validate_user_form(data, require_username=True, require_password=True, password=password)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                create_user(data["username"], password, data["role"], data["full_name"], data["email"], data["active"])
                flash("User created.", "success")
                return redirect(url_for("main.users"))
            except sqlite3.IntegrityError:
                flash("Username already exists.", "error")
            except ValueError as exc:
                flash(str(exc), "error")
    return render_template("user_form.html", data=data, roles=ROLES, mode="new")


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
@require_csrf
def edit_user(user_id):
    user_row = get_user_by_id(user_id)
    if not user_row:
        abort(404)
    data = {
        "username": user_row["username"],
        "full_name": request.form.get("full_name", user_row["full_name"] or "").strip(),
        "email": request.form.get("email", user_row["email"] or "").strip(),
        "role": request.form.get("role", user_row["role"]),
        "active": request.form.get("active", "1" if user_row["active"] else "0") == "1",
    }
    if request.method == "POST":
        errors = validate_user_form(data, require_username=False)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                update_user(user_id, data["full_name"], data["email"], data["role"], data["active"])
                flash("User updated.", "success")
                return redirect(url_for("main.users"))
            except ValueError as exc:
                flash(str(exc), "error")
    return render_template("user_form.html", data=data, user_row=user_row, roles=ROLES, mode="edit")


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
@require_csrf
def reset_user_password(user_id):
    if not get_user_by_id(user_id):
        abort(404)
    password = request.form.get("password", "")
    try:
        set_user_password(user_id, password)
        flash("Password reset.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.edit_user", user_id=user_id))


@bp.route("/users/<int:user_id>/set-active", methods=["POST"])
@admin_required
@require_csrf
def set_user_active_route(user_id):
    if not get_user_by_id(user_id):
        abort(404)
    active = request.form.get("active") == "1"
    set_user_active(user_id, active)
    flash("User activated." if active else "User deactivated.", "success")
    return redirect(url_for("main.users"))


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


def validate_user_form(data, require_username, require_password=False, password=""):
    errors = []
    if require_username and not data.get("username"):
        errors.append("Username is required.")
    if not data.get("full_name"):
        errors.append("Full name is required.")
    if data.get("role") not in ROLES:
        errors.append("Role is invalid.")
    if require_password and not password:
        errors.append("Password is required.")
    return errors
