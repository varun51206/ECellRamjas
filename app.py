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

# =====================================
# CONFIG
# =====================================
APP_TITLE = "📬 E-Cell Outreach OS (Team)"
TEAM_PASSCODE = "ecell2026"  # change this
DB_PATH = "ecell_outreach.db"

st.set_page_config(page_title=APP_TITLE, layout="wide")

# =====================================
# DEFAULT TEMPLATES
# =====================================
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
DEFAULT_OFFSETS = {"initial": 0, "f1": 3, "f2": 6, "f3": 9, "f4": 12}

# =====================================
# DB LAYER
# =====================================
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
        role TEXT,
        segment TEXT,
        owner TEXT,
        problem_area TEXT,
        status TEXT,
        stage_step TEXT,
        day_offset INTEGER,
        scheduled_date TEXT,
        last_sent_at TEXT,
        thread_id TEXT,
        notes TEXT,
        stage TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def ensure_user_profile(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_email FROM users WHERE user_email = ?", (user_email,))
    row = cur.fetchone()
    if not row:
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
    cur.execute("""
        UPDATE users SET sender_name = ?, sender_phone = ?
        WHERE user_email = ?
    """, (sender_name, sender_phone, user_email))
    conn.commit()
    conn.close()

def get_templates(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT template_key, template_value FROM templates WHERE user_email = ?", (user_email,))
    rows = cur.fetchall()
    conn.close()

    t = DEFAULT_TEMPLATES.copy()
    for k, v in rows:
        t[k] = v
    return t

def save_template(user_email, template_key, template_value):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO templates (user_email, template_key, template_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email, template_key) DO UPDATE SET
            template_value = excluded.template_value,
            updated_at = excluded.updated_at
    """, (user_email, template_key, template_value, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def clear_schedule_for_user(user_email):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM schedule WHERE user_email = ?", (user_email,))
    conn.commit()
    conn.close()

def insert_schedule_rows(user_email, rows):
    conn = db_conn()
    cur = conn.cursor()
    now_ts = datetime.now().isoformat(timespec="seconds")
    for r in rows:
        cur.execute("""
            INSERT INTO schedule (
                user_email, company, first_name, email, role, segment, owner, problem_area,
                status, stage_step, day_offset, scheduled_date, last_sent_at, thread_id, notes, stage, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_email,
            r.get("company", ""), r.get("first_name", ""), r.get("email", ""), r.get("role", ""),
            r.get("segment", ""), r.get("owner", ""), r.get("problem_area", ""),
            r.get("status", "Pending"), r.get("stage_step", ""), int(r.get("day_offset", 0)),
            r.get("scheduled_date", ""), r.get("last_sent_at", ""), r.get("thread_id", ""),
            r.get("notes", ""), r.get("stage", "Not Started"), now_ts
        ))
    conn.commit()
    conn.close()

def load_schedule_df(user_email):
    conn = db_conn()
    df = pd.read_sql_query("""
        SELECT id, company, first_name, email, role, segment, owner, problem_area,
               status, stage_step, day_offset, scheduled_date, last_sent_at, thread_id, notes, stage
        FROM schedule
        WHERE user_email = ?
        ORDER BY id ASC
    """, conn, params=(user_email,))
    conn.close()
    return df

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
        q = f"UPDATE schedule SET {', '.join(fields)} WHERE id = ?"
        vals.append(int(row_id))
        cur.execute(q, tuple(vals))

    conn.commit()
    conn.close()

def bulk_update_status_by_email(user_email, selected_email, new_status, note):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE schedule
        SET status = ?,
            stage = CASE
                WHEN ? IN ('Replied', 'Call Booked', 'Closed') THEN ?
                ELSE stage
            END,
            notes = CASE
                WHEN ? != '' THEN ?
                ELSE notes
            END
        WHERE user_email = ?
          AND email = ?
          AND status = 'Pending'
    """, (
        new_status,
        new_status, new_status,
        note, note,
        user_email, selected_email
    ))
    conn.commit()
    conn.close()

# =====================================
# HELPERS
# =====================================
def sanitize_template_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    replacements = {
        "{{First Name}}": "{{FirstName}}",
        "{{First_Name}}": "{{FirstName}}",
        "{{first_name}}": "{{FirstName}}",
        "{{Company Name}}": "{{Company}}",
        "{{Problem Area}}": "{{ProblemArea}}",
        "{{Sender Name}}": "{{SenderName}}",
        "{{Sender Phone}}": "{{SenderPhone}}",
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

def stage_from_step(step):
    return {
        "initial": "Initial Sent",
        "f1": "Follow-up 1 Sent",
        "f2": "Follow-up 2 Sent",
        "f3": "Follow-up 3 Sent",
        "f4": "Follow-up 4 Sent",
    }.get(step, "Not Started")

def get_template_keys(segment: str, step: str):
    if step == "initial":
        if str(segment).lower() == "founder":
            return "initial_founder_subject", "initial_founder_body"
        return "initial_poc_subject", "initial_poc_body"
    return f"{step}_subject", f"{step}_body"

def create_schedule_rows(base_date: datetime, lead_row: pd.Series, offsets: dict, start_step="initial"):
    rows = []
    start_index = STEP_ORDER.index(start_step)

    for step in STEP_ORDER[start_index:]:
        day_offset = int(offsets.get(step, DEFAULT_OFFSETS[step]))
        rows.append({
            "company": str(lead_row.get("company", "")).strip(),
            "first_name": str(lead_row.get("first_name", "")).strip(),
            "email": str(lead_row.get("email", "")).strip(),
            "role": str(lead_row.get("role", "")).strip(),
            "segment": str(lead_row.get("segment", "POC")).strip(),
            "owner": str(lead_row.get("owner", "")).strip(),
            "problem_area": str(lead_row.get("problem_area", "")).strip(),
            "status": "Pending",
            "stage_step": step,
            "day_offset": day_offset,
            "scheduled_date": (base_date + timedelta(days=day_offset)).date().isoformat(),
            "last_sent_at": "",
            "thread_id": "",
            "notes": "",
            "stage": "Not Started"
        })
    return rows

def send_email_smtp(
    gmail_user,
    gmail_app_password,
    to_email,
    subject,
    body,
    from_name="E-Cell Outreach",
    dry_run=True,
    attachment_bytes=None,
    attachment_name=None
):
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

# =====================================
# APP START
# =====================================
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
schedule_df = load_schedule_df(user_email)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1) Upload Leads",
    "2) Templates",
    "3) Schedule & Send",
    "4) Replies / Stop",
    "5) Export"
])

# =====================================
# TAB 1
# =====================================
with tab1:
    st.subheader("Upload leads CSV")
    st.markdown("Required columns: `company, first_name, email, role, segment, owner, problem_area`")
    st.markdown("`segment` should be `Founder` or `POC`")

    csv_file = st.file_uploader("Upload CSV", type=["csv"])
    start_date = st.date_input("Campaign start date", value=datetime.now().date())

    replace_mode = st.checkbox("Replace my existing schedule", value=True)
    start_step = st.selectbox("Start from step", STEP_ORDER, index=0)

    st.markdown("### Follow-up timing")
    c1, c2, c3, c4, c5 = st.columns(5)
    offsets = {
        "initial": c1.number_input("Initial", min_value=0, value=0, step=1),
        "f1": c2.number_input("F1", min_value=0, value=3, step=1),
        "f2": c3.number_input("F2", min_value=0, value=6, step=1),
        "f3": c4.number_input("F3", min_value=0, value=9, step=1),
        "f4": c5.number_input("F4", min_value=0, value=12, step=1),
    }

    if st.button("Generate Follow-up Schedule"):
        if csv_file is None:
            st.error("Please upload a CSV first.")
        else:
            leads = pd.read_csv(csv_file).fillna("")
            all_rows = []
            base_dt = datetime.combine(start_date, datetime.min.time())

            for _, row in leads.iterrows():
                all_rows.extend(create_schedule_rows(base_dt, row, offsets=offsets, start_step=start_step))

            if replace_mode:
                clear_schedule_for_user(user_email)

            insert_schedule_rows(user_email, all_rows)
            st.success(f"Generated {len(all_rows)} scheduled rows for {len(leads)} leads.")
            st.dataframe(load_schedule_df(user_email).head(30), use_container_width=True)

# =====================================
# TAB 2
# =====================================
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
        st.success(f"Saved template: {template_key}")
        templates = get_templates(user_email)

    st.caption("Placeholders: {{FirstName}}, {{Company}}, {{Role}}, {{ProblemArea}}, {{SenderName}}, {{SenderPhone}}")

# =====================================
# TAB 3
# =====================================
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

    today = st.date_input("Run send for date", value=datetime.now().date(), key="run_date")

    schedule_df = load_schedule_df(user_email)

    if not schedule_df.empty:
        df = schedule_df.copy()
        due = df[(df["scheduled_date"] == today.isoformat()) & (df["status"] == "Pending")].copy()

        replied_emails = set(df[df["status"].isin(["Replied", "Call Booked", "Closed"])]["email"].tolist())
        due = due[~due["email"].isin(replied_emails)]

        st.write(f"Due today: **{len(due)}**")
        st.dataframe(
            due[["id", "company", "first_name", "email", "segment", "stage_step", "scheduled_date", "status"]],
            use_container_width=True
        )

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
                    subj_template = templates.get(subj_key, "")
                    body_template = templates.get(body_key, "")

                    data = {
                        "FirstName": row["first_name"],
                        "Company": row["company"],
                        "Role": row["role"],
                        "ProblemArea": row["problem_area"],
                        "SenderName": profile["sender_name"],
                        "SenderPhone": profile["sender_phone"],
                    }

                    subject = render_template(subj_template, data)
                    body = render_template(body_template, data)

                    send_attachment_bytes = attachment_bytes if row["stage_step"] == "initial" else None
                    send_attachment_name = attachment_name if row["stage_step"] == "initial" else None

                    ok, message = send_email_smtp(
                        gmail_user=gmail_user,
                        gmail_app_password=gmail_app_password,
                        to_email=row["email"],
                        subject=subject,
                        body=body,
                        from_name=f"{profile['sender_name']} | E-Cell Ramjas",
                        dry_run=dry_run,
                        attachment_bytes=send_attachment_bytes,
                        attachment_name=send_attachment_name
                    )

                    logs.append({
                        "id": row["id"],
                        "email": row["email"],
                        "company": row["company"],
                        "step": row["stage_step"],
                        "attachment_used": "yes" if send_attachment_bytes else "no",
                        "ok": ok,
                        "message": message
                    })

                    if ok and not dry_run:
                        update_schedule_row(
                            row_id=int(row["id"]),
                            status="Sent",
                            last_sent_at=datetime.now().isoformat(timespec="seconds"),
                            stage=stage_from_step(row["stage_step"])
                        )

                    time.sleep(2)

                st.success("Send run complete.")
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
    else:
        st.info("No schedule yet. Upload leads first.")

# -----------------------------
# TAB 4
# -----------------------------
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
            use_container_width=True
        )

        new_status = st.selectbox(
            "Set lead status for all future follow-ups",
            ["Replied", "Call Booked", "Closed", "Pending"]
        )
        note = st.text_input("Add note")

        if st.button("Update lead status"):
            bulk_update_status_by_email(user_email, selected_email, new_status, note.strip())
            st.success(f"Updated status to {new_status} for {selected_email}")