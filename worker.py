import argparse
import os
import sqlite3
import time
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
import smtplib

DB_PATH = os.getenv("DB_PATH", "ecell_outreach.db")
SLEEP_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "60"))
THROTTLE_SECONDS = float(os.getenv("MAIL_THROTTLE_SECONDS", "0.5"))
STOP_STATUSES = ["Replied", "Call Booked", "Closed"]
EMERGENCY_STOP_FILE = "emergency_stop.flag"


def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def emergency_stop_active():
    return os.path.exists(EMERGENCY_STOP_FILE)


def sanitize_template_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    replacements = {
        "{{First Name}}": "{{FirstName}}", "{{First_Name}}": "{{FirstName}}", "{{first_name}}": "{{FirstName}}",
        "{{Company Name}}": "{{Company}}", "{{Problem Area}}": "{{ProblemArea}}",
        "{{Sender Name}}": "{{SenderName}}", "{{Sender Phone}}": "{{SenderPhone}}",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def render_template(text: str, data: dict) -> str:
    out = sanitize_template_text(text)
    for k, v in data.items():
        out = out.replace(f"{{{{{k}}}}}", str(v if v is not None else ""))
    return out


def get_template_keys(segment: str, step: str):
    if step == "initial":
        if str(segment).strip().lower() == "founder":
            return "initial_founder_subject", "initial_founder_body"
        return "initial_poc_subject", "initial_poc_body"
    return f"{step}_subject", f"{step}_body"


def stage_from_step(step: str):
    return {
        "initial": "Initial Sent", "f1": "Follow-up 1 Sent", "f2": "Follow-up 2 Sent",
        "f3": "Follow-up 3 Sent", "f4": "Follow-up 4 Sent",
    }.get(step, "Not Started")


def send_email_smtp(gmail_user, gmail_app_password, to_email, subject, body, from_name,
                     attachment_path="", attachment_name=""):
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{from_name} <{gmail_user}>"
        msg["To"] = to_email.strip()
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            name = attachment_name or os.path.basename(attachment_path)
            part.add_header("Content-Disposition", f'attachment; filename="{name}"')
            msg.attach(part)

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_user.strip(), gmail_app_password.strip())
            server.sendmail(gmail_user.strip(), [to_email.strip()], msg.as_string())
        return True, "Sent"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


def fetch_due_rows(conn):
    today = datetime.now().date().isoformat()
    placeholders = ",".join(["?"] * len(STOP_STATUSES))
    query = f"""
    SELECT s.id, s.company, s.first_name, s.email, s.role, s.segment, s.problem_area,
           s.stage_step, s.status,
           u.sender_name, u.sender_phone, u.gmail_user, u.gmail_app_password,
           u.lp_report_path, u.lp_report_name
    FROM schedule s
    CROSS JOIN settings u
    WHERE s.scheduled_date <= ?
      AND s.status = 'Pending'
      AND s.email NOT IN (SELECT email FROM schedule WHERE status IN ({placeholders}))
    ORDER BY s.scheduled_date ASC, s.id ASC
    """
    return conn.execute(query, (today, *STOP_STATUSES)).fetchall()


def get_templates(conn):
    rows = conn.execute("""SELECT template_key, template_value, updated_at, rowid FROM templates
        ORDER BY updated_at DESC, rowid DESC""").fetchall()
    templates = {}
    for k, v, _u, _r in rows:
        if k not in templates:
            templates[k] = v
    return templates


def mark_result(conn, row_id, ok, message, step):
    if ok:
        conn.execute("""UPDATE schedule SET status=?, last_sent_at=?, stage=?, notes=? WHERE id=?""",
                     ("Sent", datetime.now().isoformat(timespec="seconds"), stage_from_step(step), message, row_id))
    else:
        conn.execute("UPDATE schedule SET notes=? WHERE id=?", (message, row_id))
    conn.commit()


def process_once(verbose=True):
    if emergency_stop_active():
        if verbose:
            print("Emergency stop active. No emails sent.")
        return 0

    conn = db_conn()
    rows = fetch_due_rows(conn)
    processed = 0
    templates = get_templates(conn)

    for row in rows:
        (row_id, company, first_name, to_email, role, segment, problem_area, stage_step, _status,
         sender_name, sender_phone, gmail_user, gmail_app_password, lp_report_path, lp_report_name) = row

        if emergency_stop_active():
            if verbose:
                print("Emergency stop activated mid-run. Stopping now.")
            break

        if not gmail_user or not gmail_app_password:
            mark_result(conn, row_id, False, "Missing Gmail credentials in settings.", stage_step)
            continue

        subj_key, body_key = get_template_keys(segment, stage_step)
        if subj_key not in templates or body_key not in templates:
            mark_result(conn, row_id, False, f"Missing template: {subj_key} or {body_key}", stage_step)
            continue

        data = {
            "FirstName": first_name, "Company": company, "Role": role, "ProblemArea": problem_area,
            "SenderName": sender_name or "Your Name", "SenderPhone": sender_phone or "",
        }
        subject = render_template(templates[subj_key], data)
        body = render_template(templates[body_key], data)

        use_attachment_path = lp_report_path if stage_step == "initial" and lp_report_path else ""
        use_attachment_name = lp_report_name if stage_step == "initial" and lp_report_path else ""

        ok, message = send_email_smtp(
            gmail_user=gmail_user, gmail_app_password=gmail_app_password, to_email=to_email,
            subject=subject, body=body, from_name=f"{sender_name or 'Your Name'} | E-Cell Ramjas",
            attachment_path=use_attachment_path, attachment_name=use_attachment_name,
        )

        mark_result(conn, row_id, ok, message, stage_step)
        processed += 1

        if verbose:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {to_email} | {stage_step} | {message}")

        time.sleep(THROTTLE_SECONDS)

    conn.close()
    return processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process due emails once and exit")
    args = parser.parse_args()

    if args.once:
        count = process_once(verbose=True)
        print(f"Processed {count} rows")
    else:
        print(f"Worker started. Polling every {SLEEP_SECONDS} seconds. Leave this window open.")
        while True:
            try:
                count = process_once(verbose=True)
                if count:
                    print(f"Cycle complete. Processed {count} rows")
            except Exception as e:
                print(f"Worker error: {type(e).__name__}: {e}")
            time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()