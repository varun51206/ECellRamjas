import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import smtplib
import sqlite3
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

APP_TITLE = "📬 E-Cell Outreach OS (Team)"
TEAM_PASSCODE = "ecell2026"
DB_PATH = "ecell_outreach.db"

st.set_page_config(page_title=APP_TITLE, layout="wide")

DEFAULT_TEMPLATES = {
    "initial_founder_subject": "A free consulting sprint for {{Company}} — from Ramjas's E-Cell",
    "initial_founder_body": """Hi {{FirstName}},

I run the Startup Edge, Ramjas College's E-Cell at Delhi University and I'll keep this short.

We run 4-12 week "Live Projects" where a small team of our students works on one real, well-scoped problem for a company: consumer research, GTM, a pitch deck, value-chain analysis, whatever's actually keeping you up at night this quarter. No fee. No fluff. Just a signed scope, a deadline, and a deliverable your team can actually use.

We've done this recently for Rapido (UX research feeding straight into their product roadmap), Bombay Shaving Company (Gen Z research that became 4 brand reels, 100K+ views), Findoc, Piramal Foundation, CRY, and a few others. Happy to send specifics.

What we ask in return: a completion certificate for the students, and honestly, your honest feedback.

If {{Company}} has a scoped problem sitting in a backlog somewhere, market sizing, a campus GTM push, a deck that needs a rebuild, I'd love 15 minutes this week to see if it's a fit.

Worth a quick call?

{{SenderName}}
President, The Startup Edge - E-Cell, Ramjas College, University of Delhi
{{SenderPhone}}""",
    "initial_poc_subject": "16 colleges in 20 days, 100K+ views, one Rapido roadmap, {{Company}} could be next",
    "initial_poc_body": """Hi {{FirstName}},

Quick context before the ask: I lead The Startup Edge, the E-Cell at Ramjas College, University of Delhi. We run structured "Live Projects", student consulting teams embedded on a single, real business problem for 4-12 weeks.

A few recent outcomes:
- Rapido: field research with Captain-app drivers, delivered straight to their Product & Research heads as a roadmap input
- Bombay Shaving Company: Gen Z consumer research that directly shaped 4 brand reels (100K+ views)
- Zyber: scaled a campus rollout from 0 to 16 colleges and 1,000+ users in 20 days
- Piramal Foundation, Findoc, CRY, Poshn, Teach For India, United Way of Delhi - research, GTM, and strategy work across sectors

The deal is simple: no cost to you, a defined scope and timeline, C-suite-level delivery at the end, and in exchange, a certificate confirming the students worked under your team.

Open to a short call this week to see if there's a specific problem worth scoping?

Best,
{{SenderName}}
{{SenderPhone}}""",
    "f1_subject": "Re: quick idea for {{Company}}",
    "f1_body": """Hi {{FirstName}},

Just bumping this in case it got buried.

If useful, we can take one scoped problem off your team’s plate for 4-12 weeks (no fee) and deliver a concrete output your team can use immediately.

Open to a 15-min call this week?

Best,
{{SenderName}}""",
    "f2_subject": "Re: free live project support for {{Company}}",
    "f2_body": """Hi {{FirstName}},

Quick context on outcomes we’ve delivered:

- Rapido: field UX research used as roadmap input
- Bombay Shaving Company: Gen Z research shaping branded content
- Zyber: campus rollout support across 16 colleges in 20 days

Format is simple: one real problem, defined scope, fixed timeline, final deliverable.

Would you like us to suggest 2-3 possible problem statements for {{Company}}?

Best,
{{SenderName}}""",
    "f3_subject": "Re: should we propose a scoped sprint for {{Company}}?",
    "f3_body": """Hi {{FirstName}},

To make this easy, here are projects we can execute quickly:

1) Consumer/market research sprint
2) Campus GTM pilot + feedback loop
3) Pitch deck / narrative rebuild
4) Competitor or value-chain analysis

If you share one priority area, I can send a one-page scope + timeline.

Worth exploring?

Best,
{{SenderName}}""",
    "f4_subject": "Re: close this thread?",
    "f4_body": """Hi {{FirstName}},

I know inboxes are packed, so I’ll keep this short.

If this isn’t a priority right now, no worries — happy to close the loop.
If it is, I can send a draft scope for one problem area.

Should I close this for now?

Best,
{{SenderName}}"""
}

STEP_ORDER = ["initial", "f1", "f2", "f3", "f4"]
DEFAULT_GAPS = {"f1": 3, "f2": 3, "f3": 3, "f4": 3}
STOP_STATUSES = ["Replied", "Call Booked", "Closed"]


def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_email TEXT PRIMARY KEY,
        sender_name TEXT,
        sender_phone TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        template_key TEXT,
        template_value TEXT,
        updated_at TEXT,
        UNIQUE(user_email, template_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT,
        company TEXT,
        first_name TEXT,
        email TEXT,
        segment TEXT,
        status TEXT,
        stage_step TEXT,
        step_order INTEGER,
        scheduled_date TEXT,
        last_sent_at TEXT,
        notes TEXT,
        stage TEXT,
        created_at TEXT,
        UNIQUE(user_email, email, stage_step)
    )
    """)

    conn.commit()

    existing_cols = [r[1] for r in cur.execute("PRAGMA table_info(schedule)").fetchall()]
    migration_cols = {
        "company": "TEXT",
        "first_name": "TEXT",
        "email": "TEXT",
        "segment": "TEXT",
        "status": "TEXT",
        "stage_step": "TEXT",
        "step_order": "INTEGER",
        "scheduled_date": "TEXT",
        "last_sent_at": "TEXT",
        "notes": "TEXT",
        "stage": "TEXT",
        "created_at": "TEXT",
    }
    for col, col_type in migration_cols.items():
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE schedule ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()


def ensure_user_profile(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_email FROM users WHERE user_email = ?", (user_email,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_email, sender_name, sender_phone) VALUES (?, ?, ?)",
            (user_email, "Your Name", "+91 XXXXX XXXXX")
        )
    conn.commit()
    conn.close()


def get_user_profile(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT sender_name, sender_phone FROM users WHERE user_email = ?", (user_email,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"sender_name": row[0] or "Your Name", "sender_phone": row[1] or "+91 XXXXX XXXXX"}
    return {"sender_name": "Your Name", "sender_phone": "+91 XXXXX XXXXX"}


def update_user_profile(user_email, sender_name, sender_phone):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET sender_name = ?, sender_phone = ? WHERE user_email = ?",
        (sender_name, sender_phone, user_email)
    )
    conn.commit()
    conn.close()


def get_templates(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT template_key, template_value FROM templates WHERE user_email = ?", (user_email,))
    rows = cur.fetchall()
    conn.close()
    data = DEFAULT_TEMPLATES.copy()
    for k, v in rows:
        data[k] = v
    return data


def save_template(user_email, template_key, template_value):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO templates (user_email, template_key, template_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email, template_key) DO UPDATE SET
            template_value = excluded.template_value,
            updated_at = excluded.updated_at
        """,
        (user_email, template_key, template_value, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def load_schedule_df(user_email):
    conn = db_conn()
    df = pd.read_sql_query(
        """
        SELECT id, company, first_name, email, segment, status, stage_step, step_order,
               scheduled_date, last_sent_at, notes, stage
        FROM schedule
        WHERE user_email = ?
        ORDER BY email ASC, step_order ASC, id ASC
        """,
        conn,
        params=(user_email,)
    )
    conn.close()
    return df


def clear_schedule_for_user(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM schedule WHERE user_email = ?", (user_email,))
    conn.commit()
    conn.close()


def sanitize_template_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    replacements = {
        "{{First Name}}": "{{FirstName}}",
        "{{First_Name}}": "{{FirstName}}",
        "{{first_name}}": "{{FirstName}}",
        "{{Company Name}}": "{{Company}}",
        "{{Sender Name}}": "{{SenderName}}",
        "{{Sender Phone}}": "{{SenderPhone}}",
        "{{Role}}": "",
        "{{ProblemArea}}": "",
        "{{Problem Area}}": "",
    }
    out = text
    for bad, good in replacements.items():
        out = out.replace(bad, good)
    return out


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
        "initial": "Initial Sent",
        "f1": "Follow-up 1 Sent",
        "f2": "Follow-up 2 Sent",
        "f3": "Follow-up 3 Sent",
        "f4": "Follow-up 4 Sent",
    }.get(step, "Not Started")


def normalize_segment(value: str) -> str:
    return "Founder" if str(value).strip().lower() == "founder" else "POC"


def compute_offsets(gaps: dict):
    offsets = {"initial": 0}
    running = 0
    for step in ["f1", "f2", "f3", "f4"]:
        running += int(gaps.get(step, 3))
        offsets[step] = running
    return offsets


def build_rows_for_lead(lead: dict, base_date: datetime, gaps: dict, start_step: str):
    offsets = compute_offsets(gaps)
    start_index = STEP_ORDER.index(start_step)
    rows = []
    for order_idx, step in enumerate(STEP_ORDER[start_index:], start=start_index):
        rows.append({
            "company": lead.get("company", ""),
            "first_name": lead.get("first_name", ""),
            "email": lead.get("email", "").strip().lower(),
            "segment": normalize_segment(lead.get("segment", "POC")),
            "status": "Pending",
            "stage_step": step,
            "step_order": order_idx,
            "scheduled_date": (base_date + timedelta(days=offsets[step])).date().isoformat(),
            "last_sent_at": "",
            "notes": "",
            "stage": "Not Started",
        })
    return rows


def upsert_schedule_rows(user_email, rows):
    conn = db_conn()
    cur = conn.cursor()
    now_ts = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    skipped = 0
    for r in rows:
        try:
            cur.execute(
                """
                INSERT INTO schedule (
                    user_email, company, first_name, email, segment, status,
                    stage_step, step_order, scheduled_date, last_sent_at, notes, stage, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_email,
                    r.get("company", ""), r.get("first_name", ""), r.get("email", ""), r.get("segment", "POC"),
                    r.get("status", "Pending"), r.get("stage_step", ""), int(r.get("step_order", 0)),
                    r.get("scheduled_date", ""), r.get("last_sent_at", ""), r.get("notes", ""),
                    r.get("stage", "Not Started"), now_ts,
                )
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    conn.close()
    return inserted, skipped


def prepare_uploaded_leads(files):
    all_frames = []
    for file in files:
        df = pd.read_csv(file).fillna("")
        df.columns = [str(c).strip().lower() for c in df.columns]
        all_frames.append(df)
    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)
    required = ["company", "first_name", "email", "segment"]
    missing = [c for c in required if c not in combined.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    keep_cols = [c for c in required if c in combined.columns]
    if "start_step" in combined.columns:
        keep_cols.append("start_step")
    if "start_date" in combined.columns:
        keep_cols.append("start_date")

    combined = combined[keep_cols].copy()
    combined["email"] = combined["email"].astype(str).str.strip().str.lower()
    combined["company"] = combined["company"].astype(str).str.strip()
    combined["first_name"] = combined["first_name"].astype(str).str.strip()
    combined["segment"] = combined["segment"].apply(normalize_segment)
    if "start_step" in combined.columns:
        combined["start_step"] = combined["start_step"].astype(str).str.strip().str.lower()
        combined.loc[~combined["start_step"].isin(STEP_ORDER), "start_step"] = "initial"
    else:
        combined["start_step"] = "initial"

    combined = combined[combined["email"] != ""].copy()
    combined = combined.drop_duplicates(subset=["email"], keep="first").reset_index(drop=True)
    return combined


def recalculate_future_rows(user_email, email, start_step, anchor_date, gaps):
    conn = db_conn()
    cur = conn.cursor()
    anchor_dt = datetime.combine(anchor_date, datetime.min.time())
    start_index = STEP_ORDER.index(start_step)
    stop_steps = STEP_ORDER[start_index:]

    cur.execute(
        """
        SELECT company, first_name, email, segment
        FROM schedule
        WHERE user_email = ? AND email = ?
        ORDER BY id ASC LIMIT 1
        """,
        (user_email, email)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "Lead not found"

    lead = {
        "company": row[0] or "",
        "first_name": row[1] or "",
        "email": row[2] or "",
        "segment": row[3] or "POC",
    }

    cur.execute(
        f"DELETE FROM schedule WHERE user_email = ? AND email = ? AND stage_step IN ({','.join(['?'] * len(stop_steps))}) AND status = 'Pending'",
        (user_email, email, *stop_steps)
    )

    new_rows = build_rows_for_lead(lead, anchor_dt, gaps, start_step)
    now_ts = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    skipped = 0
    for r in new_rows:
        try:
            cur.execute(
                """
                INSERT INTO schedule (
                    user_email, company, first_name, email, segment, status,
                    stage_step, step_order, scheduled_date, last_sent_at, notes, stage, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_email,
                    r["company"], r["first_name"], r["email"], r["segment"], r["status"],
                    r["stage_step"], r["step_order"], r["scheduled_date"], r["last_sent_at"],
                    r["notes"], r["stage"], now_ts,
                )
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()
    return True, f"Rebuilt future steps. Inserted: {inserted}, skipped duplicates: {skipped}"


def update_schedule_row(row_id, status=None, last_sent_at=None, stage=None, notes=None):
    conn = db_conn()
    cur = conn.cursor()
    fields = []
    vals = []
    if status is not None:
        fields.append("status = ?")
        vals.append(status)
    if last_sent_at is not None:
        fields.append("last_sent_at = ?")
        vals.append(last_sent_at)
    if stage is not None:
        fields.append("stage = ?")
        vals.append(stage)
    if notes is not None:
        fields.append("notes = ?")
        vals.append(notes)
    if fields:
        vals.append(int(row_id))
        cur.execute(f"UPDATE schedule SET {', '.join(fields)} WHERE id = ?", tuple(vals))
    conn.commit()
    conn.close()


def bulk_update_status_by_email(user_email, selected_email, new_status, note):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE schedule
        SET status = ?,
            stage = CASE WHEN ? IN ('Replied', 'Call Booked', 'Closed') THEN ? ELSE stage END,
            notes = CASE WHEN ? != '' THEN ? ELSE notes END
        WHERE user_email = ?
          AND email = ?
          AND status = 'Pending'
        """,
        (new_status, new_status, new_status, note, note, user_email, selected_email)
    )
    conn.commit()
    conn.close()


def send_email_smtp(gmail_user, gmail_app_password, to_email, subject, body, from_name="E-Cell Outreach", dry_run=True, attachment_bytes=None, attachment_name=None):
    if dry_run:
        return False, "DRY_RUN: Email not sent."
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{from_name} <{gmail_user}>"
        msg["To"] = to_email.strip()
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if attachment_bytes and attachment_name:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
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


init_db()

st.title(APP_TITLE)

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""

with st.sidebar:
    st.markdown("## Team Login")
    if not st.session_state.auth_ok:
        entered_email = st.text_input("Your E-Cell email")
        entered_passcode = st.text_input("Team passcode", type="password")
        if st.button("Login"):
            if entered_passcode == TEAM_PASSCODE and entered_email.strip():
                st.session_state.auth_ok = True
                st.session_state.user_email = entered_email.strip().lower()
                ensure_user_profile(st.session_state.user_email)
                st.success("Logged in")
                st.rerun()
            else:
                st.error("Invalid passcode or missing email.")
    else:
        st.success(f"Logged in as: {st.session_state.user_email}")
        if st.button("Logout"):
            st.session_state.auth_ok = False
            st.session_state.user_email = ""
            st.rerun()

if not st.session_state.auth_ok:
    st.info("Please login from the sidebar to continue.")
    st.stop()

user_email = st.session_state.user_email
profile = get_user_profile(user_email)
templates = get_templates(user_email)

base_tabs = st.tabs([
    "1) Upload Leads",
    "2) Templates",
    "3) Schedule & Send",
    "4) Replies / Stop",
    "5) Lead Controls",
    "6) Export",
])

tab1, tab2, tab3, tab4, tab5, tab6 = base_tabs

with tab1:
    st.subheader("Upload leads CSV files")
    st.markdown("Required columns: `company, first_name, email, segment`")
    st.markdown("Optional per-row columns: `start_step`, `start_date`")
    st.markdown("`segment` should be `Founder` or anything else for `POC`")

    csv_files = st.file_uploader("Upload one or more CSV files", type=["csv"], accept_multiple_files=True)
    default_start_date = st.date_input("Default campaign start date", value=datetime.now().date())
    replace_mode = st.checkbox("Replace my existing schedule", value=False)

    st.markdown("### Default follow-up spacing")
    g1, g2, g3, g4 = st.columns(4)
    gaps = {
        "f1": g1.number_input("Days to F1", min_value=0, value=3, step=1),
        "f2": g2.number_input("Days after F1 to F2", min_value=0, value=3, step=1),
        "f3": g3.number_input("Days after F2 to F3", min_value=0, value=3, step=1),
        "f4": g4.number_input("Days after F3 to F4", min_value=0, value=3, step=1),
    }
    default_start_step = st.selectbox("Default start step", STEP_ORDER, index=0)

    if st.button("Generate / Add Schedule"):
        if not csv_files:
            st.error("Please upload at least one CSV file.")
        else:
            try:
                leads = prepare_uploaded_leads(csv_files)
                if leads.empty:
                    st.warning("No valid leads found after cleaning the CSV files.")
                else:
                    if replace_mode:
                        clear_schedule_for_user(user_email)

                    all_rows = []
                    for _, row in leads.iterrows():
                        row_start_step = row.get("start_step", default_start_step)
                        if row_start_step not in STEP_ORDER:
                            row_start_step = default_start_step

                        if "start_date" in leads.columns and str(row.get("start_date", "")).strip():
                            try:
                                row_base_date = pd.to_datetime(row.get("start_date")).date()
                            except Exception:
                                row_base_date = default_start_date
                        else:
                            row_base_date = default_start_date

                        all_rows.extend(
                            build_rows_for_lead(
                                lead=row.to_dict(),
                                base_date=datetime.combine(row_base_date, datetime.min.time()),
                                gaps=gaps,
                                start_step=row_start_step,
                            )
                        )

                    inserted, skipped = upsert_schedule_rows(user_email, all_rows)
                    st.success(f"Schedule updated. Inserted {inserted} rows, skipped {skipped} duplicate rows.")
                    st.dataframe(load_schedule_df(user_email), use_container_width=True)
            except Exception as e:
                st.error(str(e))

with tab2:
    st.subheader("Edit templates (your personal copy)")
    sender_name = st.text_input("Sender name", value=profile["sender_name"])
    sender_phone = st.text_input("Sender phone", value=profile["sender_phone"])

    if st.button("Save sender profile"):
        update_user_profile(user_email, sender_name, sender_phone)
        st.success("Sender profile saved.")
        profile = get_user_profile(user_email)

    template_key = st.selectbox("Choose template", list(templates.keys()))
    edited = st.text_area("Template content", templates[template_key], height=320)

    if st.button("Save Template"):
        clean = sanitize_template_text(edited)
        save_template(user_email, template_key, clean)
        templates = get_templates(user_email)
        st.success(f"Saved template: {template_key}")

    st.caption("Placeholders: {{FirstName}}, {{Company}}, {{SenderName}}, {{SenderPhone}}")

with tab3:
    st.subheader("Send scheduled emails")
    c1, c2, c3 = st.columns(3)
    gmail_user = c1.text_input("Gmail address")
    gmail_app_password = c2.text_input("Gmail App Password", type="password")
    dry_run = c3.checkbox("Dry run (preview only)", value=True)

    lp_file = st.file_uploader(
        "Attach LP report (PDF/PPT/PPTX) - sent ONLY on initial mail",
        type=["pdf", "ppt", "pptx"],
        key="lp_attach"
    )
    run_date = st.date_input("Run send for date", value=datetime.now().date())

    schedule_df = load_schedule_df(user_email)
    if schedule_df.empty:
        st.info("No schedule yet. Upload leads first.")
    else:
        due = schedule_df[(schedule_df["scheduled_date"] == run_date.isoformat()) & (schedule_df["status"] == "Pending")].copy()
        blocked_emails = set(schedule_df[schedule_df["status"].isin(STOP_STATUSES)]["email"].tolist())
        due = due[~due["email"].isin(blocked_emails)]

        st.write(f"Due today: **{len(due)}**")
        st.dataframe(due[["id", "company", "first_name", "email", "segment", "stage_step", "scheduled_date", "status"]], use_container_width=True)

        if st.button("Send all due emails now"):
            if not dry_run and (not gmail_user or not gmail_app_password):
                st.error("Please enter Gmail and App Password, or enable Dry Run.")
            else:
                templates = get_templates(user_email)
                profile = get_user_profile(user_email)
                attachment_bytes = lp_file.read() if lp_file else None
                attachment_name = lp_file.name if lp_file else None

                logs = []
                for _, row in due.iterrows():
                    subj_key, body_key = get_template_keys(row["segment"], row["stage_step"])
                    data = {
                        "FirstName": row["first_name"],
                        "Company": row["company"],
                        "SenderName": profile["sender_name"],
                        "SenderPhone": profile["sender_phone"],
                    }
                    subject = render_template(templates.get(subj_key, ""), data)
                    body = render_template(templates.get(body_key, ""), data)

                    use_attachment_bytes = attachment_bytes if row["stage_step"] == "initial" else None
                    use_attachment_name = attachment_name if row["stage_step"] == "initial" else None

                    ok, message = send_email_smtp(
                        gmail_user=gmail_user,
                        gmail_app_password=gmail_app_password,
                        to_email=row["email"],
                        subject=subject,
                        body=body,
                        from_name=f"{profile['sender_name']} | E-Cell Ramjas",
                        dry_run=dry_run,
                        attachment_bytes=use_attachment_bytes,
                        attachment_name=use_attachment_name,
                    )

                    logs.append({
                        "id": row["id"],
                        "email": row["email"],
                        "company": row["company"],
                        "step": row["stage_step"],
                        "attachment_used": "yes" if use_attachment_bytes else "no",
                        "ok": ok,
                        "message": message,
                    })

                    if ok and not dry_run:
                        update_schedule_row(
                            row_id=int(row["id"]),
                            status="Sent",
                            last_sent_at=datetime.now().isoformat(timespec="seconds"),
                            stage=stage_from_step(row["stage_step"]),
                        )

                    time.sleep(2)

                st.success("Send run complete.")
                st.dataframe(pd.DataFrame(logs), use_container_width=True)

with tab4:
    st.subheader("Mark replies / stop follow-ups")
    schedule_df = load_schedule_df(user_email)

    if schedule_df.empty:
        st.info("No data yet.")
    else:
        email_list = sorted(schedule_df["email"].dropna().unique().tolist())
        selected_email = st.selectbox("Select lead email", email_list)

        lead_rows = schedule_df[schedule_df["email"] == selected_email].copy()
        st.dataframe(
            lead_rows[["id", "company", "first_name", "email", "segment", "stage_step", "scheduled_date", "status", "notes"]],
            use_container_width=True,
        )

        new_status = st.selectbox("Set lead status for all future follow-ups", ["Replied", "Call Booked", "Closed", "Pending"])
        note = st.text_input("Add note")

        if st.button("Update lead status"):
            bulk_update_status_by_email(user_email, selected_email, new_status, note.strip())
            st.success(f"Updated status to {new_status} for {selected_email}")

with tab5:
    st.subheader("Lead Controls")
    schedule_df = load_schedule_df(user_email)
    if schedule_df.empty:
        st.info("No leads yet.")
    else:
        unique_leads = schedule_df[["email", "company", "first_name", "segment"]].drop_duplicates().sort_values(by=["company", "email"])
        selected_email = st.selectbox("Choose a lead to edit future follow-ups", unique_leads["email"].tolist(), key="lead_controls_email")
        lead_rows = schedule_df[schedule_df["email"] == selected_email].copy()
        st.dataframe(lead_rows[["company", "first_name", "email", "segment", "stage_step", "scheduled_date", "status"]], use_container_width=True)

        current_pending = lead_rows[lead_rows["status"] == "Pending"]
        suggested_start = current_pending["stage_step"].iloc[0] if not current_pending.empty else "f1"
        new_start_step = st.selectbox("Restart / begin future schedule from", STEP_ORDER, index=STEP_ORDER.index(suggested_start), key="edit_start_step")
        new_anchor_date = st.date_input("Start this revised future schedule from", value=datetime.now().date(), key="edit_start_date")

        st.markdown("### Custom spacing for this person")
        p1, p2, p3, p4 = st.columns(4)
        person_gaps = {
            "f1": p1.number_input("Days to F1", min_value=0, value=3, step=1, key="person_f1"),
            "f2": p2.number_input("Days after F1 to F2", min_value=0, value=3, step=1, key="person_f2"),
            "f3": p3.number_input("Days after F2 to F3", min_value=0, value=3, step=1, key="person_f3"),
            "f4": p4.number_input("Days after F3 to F4", min_value=0, value=3, step=1, key="person_f4"),
        }

        if st.button("Rebuild future follow-ups for this lead"):
            ok, message = recalculate_future_rows(user_email, selected_email, new_start_step, new_anchor_date, person_gaps)
            if ok:
                st.success(message)
            else:
                st.error(message)

with tab6:
    st.subheader("Export")
    out = load_schedule_df(user_email)
    if out.empty:
        st.info("Nothing to export yet.")
    else:
        st.dataframe(out, use_container_width=True)
        csv_bytes = out.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download outreach_schedule.csv",
            data=csv_bytes,
            file_name=f"outreach_schedule_{user_email.replace('@', '_at_')}.csv",
            mime="text/csv",
        )

        st.markdown("### KPI Snapshot")
        total = len(out["email"].unique())
        replied = len(out[out["status"] == "Replied"]["email"].unique())
        booked = len(out[out["status"] == "Call Booked"]["email"].unique())
        closed = len(out[out["status"] == "Closed"]["email"].unique())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Leads", total)
        c2.metric("Replied", replied)
        c3.metric("Calls Booked", booked)
        c4.metric("Closed", closed)