from datetime import date, datetime, timezone

from models import ACTIVE, COMPLETED, ON_HOLD, RELEASED, RESALE_REQUESTED


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(value).date()


def _today(today=None):
    return today or date.today()


def calculate_days_open(job, today=None):
    received = _parse_date(job["date_received"])
    if not received:
        return None
    end = _today(today)
    if job["job_status"] == COMPLETED and job["completed_at"]:
        end = _parse_date(job["completed_at"])
    return max((end - received).days, 0)


def calculate_days_on_hold(job, today=None):
    if job["release_status"] != ON_HOLD:
        return None
    start = _parse_date(
        job["hold_started_at"]
        or job["updated_at"]
        or job["date_received"]
    )
    if not start:
        return None
    return max((_today(today) - start).days, 0)


def calculate_days_since_released(job, today=None):
    if job["release_status"] != RELEASED or not job["released_at"]:
        return None
    released = _parse_date(job["released_at"])
    return max((_today(today) - released).days, 0)


def calculate_days_since_resale_requested(job, today=None):
    if job["resale_status"] != RESALE_REQUESTED or not job["resale_requested_at"]:
        return None
    requested = _parse_date(job["resale_requested_at"])
    return max((_today(today) - requested).days, 0)


def get_aging_level(days, aging_type):
    if days is None:
        return "normal"
    if aging_type in {"days_open", "days_on_hold"}:
        if days >= 6:
            return "urgent"
        if days >= 3:
            return "warning"
        return "normal"
    if aging_type in {"days_since_released", "days_since_resale_requested"}:
        if days >= 4:
            return "urgent"
        if days >= 2:
            return "warning"
        return "normal"
    return "normal"


def get_attention_reasons(job, today=None):
    if job["job_status"] != ACTIVE:
        return []

    reasons = []
    days_open = calculate_days_open(job, today)
    days_on_hold = calculate_days_on_hold(job, today)
    days_released = calculate_days_since_released(job, today)
    days_resale = calculate_days_since_resale_requested(job, today)

    if job["release_status"] == ON_HOLD:
        reasons.append(
            {
                "label": "Waiting for Release",
                "owner": "Account Manager",
                "level": "attention",
            }
        )

    if job["resale_status"] == RESALE_REQUESTED:
        reasons.append(
            {
                "label": "Resale Numbers Needed",
                "owner": "Warehouse Manager / Operations",
                "level": "attention",
            }
        )

    if days_released is not None and days_released > 2:
        reasons.append(
            {
                "label": "Released, Not Completed",
                "owner": "Warehouse Manager",
                "level": get_aging_level(days_released, "days_since_released"),
            }
        )

    if days_open is not None and days_open > 5:
        reasons.append(
            {
                "label": "Active Over 5 Days",
                "owner": "Warehouse Manager / Admin",
                "level": get_aging_level(days_open, "days_open"),
            }
        )

    if days_resale is not None and days_resale > 3:
        reasons.append(
            {
                "label": "Resale Request Over 3 Days",
                "owner": "Warehouse Manager / Operations",
                "level": get_aging_level(days_resale, "days_since_resale_requested"),
            }
        )

    if days_on_hold is not None and days_on_hold > 5:
        reasons.append(
            {
                "label": "Long Hold",
                "owner": "Account Manager",
                "level": get_aging_level(days_on_hold, "days_on_hold"),
            }
        )

    return reasons


def job_needs_attention(job, today=None):
    return bool(get_attention_reasons(job, today))


def get_suggested_owners(reasons):
    owners = []
    for reason in reasons:
        owner = reason["owner"]
        if owner not in owners:
            owners.append(owner)
    return owners
