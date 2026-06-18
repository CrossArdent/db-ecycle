from functools import wraps
from secrets import token_urlsafe

from flask import abort, flash, redirect, request, session, url_for

from models import ROLE_ADMIN, ROLE_DISPLAY, get_user_by_id


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if current_user() is None:
            return redirect(url_for("main.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("main.login", next=request.path))
        if user["role"] != ROLE_ADMIN:
            abort(403)
        return view(**kwargs)

    return wrapped_view


def non_display_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("main.login", next=request.path))
        if user["role"] == ROLE_DISPLAY:
            abort(403)
        return view(**kwargs)

    return wrapped_view


def generate_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    token = session.get("csrf_token")
    submitted = request.form.get("csrf_token")
    if not token or not submitted or token != submitted:
        abort(400, "Invalid CSRF token")


def require_csrf(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if request.method == "POST":
            validate_csrf()
        return view(**kwargs)

    return wrapped_view


def can_create_job(user):
    return user and user["role"] != ROLE_DISPLAY


def can_release_job(user):
    return user and user["role"] in {"Admin", "Account Manager"}


def can_hold_job(user):
    return user and user["role"] in {"Admin", "Account Manager", "Warehouse Manager"}


def can_complete_job(user):
    return user and user["role"] in {"Admin", "Warehouse Manager"}


def can_reopen_job(user):
    return user and user["role"] == ROLE_ADMIN


def can_delete_job(user):
    return user and user["role"] == ROLE_ADMIN


def editable_fields_for(user):
    if not user:
        return []
    if user["role"] == "Admin":
        return ["order_number", "customer_name", "date_received", "release_status", "job_status", "notes"]
    if user["role"] == "Account Manager":
        return ["order_number", "customer_name", "date_received", "notes"]
    if user["role"] == "Warehouse Manager":
        return ["notes"]
    return []


def flash_authorization_error(message):
    flash(message, "error")
