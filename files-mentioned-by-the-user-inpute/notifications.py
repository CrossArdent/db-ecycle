import logging
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_release_email(job, released_by, released_at):
    required = [
        "SMTP_HOST",
        "SMTP_FROM",
        "WAREHOUSE_MANAGER_EMAIL",
    ]
    missing = [key for key in required if not current_app.config.get(key)]
    if missing:
        message = "Email not sent because SMTP settings are missing: " + ", ".join(missing)
        current_app.logger.warning(message)
        return False, message

    msg = EmailMessage()
    msg["Subject"] = f"Job Released - Order #{job['order_number']} - {job['customer_name']}"
    msg["From"] = current_app.config["SMTP_FROM"]
    msg["To"] = current_app.config["WAREHOUSE_MANAGER_EMAIL"]
    msg.set_content(
        "\n".join(
            [
                f"Order #{job['order_number']} for {job['customer_name']} has been released and is ready for warehouse processing.",
                "",
                f"Released by: {released_by}",
                f"Released at: {released_at}",
                f"Notes: {job['notes'] or ''}",
            ]
        )
    )

    try:
        with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10) as smtp:
            smtp.starttls()
            username = current_app.config.get("SMTP_USERNAME")
            password = current_app.config.get("SMTP_PASSWORD")
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:
        logging.exception("Release email failed")
        return False, f"Release succeeded, but email notification failed: {exc}"

    return True, "Release email sent."
