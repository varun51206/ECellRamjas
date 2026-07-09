import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import os
import time

APP_TITLE = "E-Cell Outreach OS"
DB_PATH = "ecell_outreach.db"
ATTACH_DIR = "attachments"
EMERGENCY_STOP_FILE = "emergency_stop.flag"

os.makedirs(ATTACH_DIR, exist_ok=True)

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

If useful, we can take one scoped problem off your team's plate for 4-12 weeks (no fee) and deliver a concrete output your team can use immediately.

Open to a 15-min call this week?

Best,
{{SenderName}}
{{SenderPhone}}""",
    "f2_subject": "Re: free live project support for {{Company}}",
    "f2_body": """Hi {{FirstName}},

Quick context on outcomes we've delivered:

- Rapido: field UX research used as roadmap input
- Bombay Shaving Company: Gen Z research shaping branded content
- Zyber: campus rollout support across 16 colleges in 20 days

Format is simple: one real problem, defined scope, fixed timeline, final deliverable.

Would you like us to suggest 2-3 possible problem statements for {{Company}}?

Best,
{{SenderName}}
{{SenderPhone}}""",
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
{{SenderName}}
{{SenderPhone}}""",
    "f4_subject": "Re: close this thread?",
    "f4_body": """Hi {{FirstName}},

I know inboxes are packed, so I'll keep this short.

If this isn't a priority right now, no worries — happy to close the loop.
If it is, I can send a draft scope for one problem area.

Should I close this for now?

Best,
{{SenderName}}
{{SenderPhone}}"""
}

STEP_ORDER = ["initial", "f1", "f2", "f3", "f4"]
DEFAULT_OFFSETS = {"initial": 0, "f1": 3, "f2": 6, "f3": 9, "f4": 12}
STOP_STATUSES = ["Replied", "Call Booked", "Closed"]


def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        sender_name TEXT, sender_phone TEXT, gmail_user TEXT, gmail_app_password TEXT,
        lp_report_path TEXT, lp_report_name TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS templates (
        template_key TEXT, template_value TEXT, updated_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT, first_name TEXT, email TEXT,
        role TEXT, segment TEXT, owner TEXT, problem_area TEXT, status TEXT, stage_step TEXT,
        day_offset INTEGER, step_order INTEGER, scheduled_date TEXT, last_sent_at TEXT,
        notes TEXT, stage TEXT, created_at TEXT)""")
    cur.execute("""INSERT OR IGNORE INTO settings
        (id, sender_name, sender_phone, gmail_user, gmail_app_password, lp_report_path, lp_report_name)
        VALUES (1, 'Your Name', '+91 XXXXX XXXXX', '', '', '', '')""")
    existing_keys = {r[0] for r in cur.execute("SELECT template_key FROM templates").fetchall()}
    for k, v in DEFAULT_TEMPLATES.items():
        if k not in existing_keys:
            cur.execute("INSERT INTO templates (template_key, template_value, updated_at) VALUES (?, ?, ?)",
                        (k, v, datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    conn.close()


def get_settings():
    conn = db_conn()
    row = conn.execute("""SELECT sender_name, sender_phone, gmail_user, gmail_app_password,
        lp_report_path, lp_report_name FROM settings WHERE id = 1""").fetchone()
    conn.close()
    if row:
        return {"sender_name": row[0] or "Your Name", "sender_phone": row[1] or "",
                "gmail_user": row[2] or "", "gmail_app_password": row[3] or "",
                "lp_report_path": row[4] or "", "lp_report_name": row[5] or ""}
    return {"sender_name": "Your Name", "sender_phone": "", "gmail_user": "",
            "gmail_app_password": "", "lp_report_path": "", "lp_report_name": ""}


def update_settings(sender_name, sender_phone, gmail_user, gmail_app_password):
    conn = db_conn()
    conn.execute("""UPDATE settings SET sender_name=?, sender_phone=?, gmail_user=?,
        gmail_app_password=? WHERE id=1""", (sender_name, sender_phone, gmail_user, gmail_app_password))
    conn.commit()
    conn.close()


def save_lp_report(uploaded_file):
    ext = os.path.splitext(uploaded_file.name)[1]
    dest_path = os.path.join(ATTACH_DIR, f"lp_report{ext}")
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    conn = db_conn()
    conn.execute("UPDATE settings SET lp_report_path=?, lp_report_name=? WHERE id=1",
                 (dest_path, uploaded_file.name))
    conn.commit()
    conn.close()


def remove_lp_report():
    conn = db_conn()
    conn.execute("UPDATE settings SET lp_report_path='', lp_report_name='' WHERE id=1")
    conn.commit()
    conn.close()


def get_templates():
    conn = db_conn()
    rows = conn.execute("""SELECT template_key, template_value, updated_at, rowid FROM templates
        ORDER BY updated_at DESC, rowid DESC""").fetchall()
    conn.close()
    t = DEFAULT_TEMPLATES.copy()
    seen = set()
    for k, v, _u, _r in rows:
        if k not in seen:
            t[k] = v
            seen.add(k)
    return t


def save_template(template_key, template_value):
    conn = db_conn()
    cur = conn.cursor()
    existing = cur.execute("""SELECT rowid FROM templates WHERE template_key=?
        ORDER BY updated_at DESC, rowid DESC LIMIT 1""", (template_key,)).fetchone()
    if existing:
        cur.execute("UPDATE templates SET template_value=?, updated_at=? WHERE rowid=?",
                    (template_value, datetime.now().isoformat(timespec='seconds'), existing[0]))
    else:
        cur.execute("INSERT INTO templates (template_key, template_value, updated_at) VALUES (?, ?, ?)",
                    (template_key, template_value, datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    conn.close()


def clear_schedule():
    conn = db_conn()
    conn.execute("DELETE FROM schedule")
    conn.commit()
    conn.close()


def insert_schedule_rows(rows):
    conn = db_conn()
    cur = conn.cursor()
    now_ts = datetime.now().isoformat(timespec='seconds')
    for r in rows:
        cur.execute("""INSERT INTO schedule (company, first_name, email, role, segment, owner,
            problem_area, status, stage_step, day_offset, step_order, scheduled_date, last_sent_at,
            notes, stage, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            r.get("company",""), r.get("first_name",""), r.get("email",""), r.get("role",""),
            r.get("segment","POC"), r.get("owner",""), r.get("problem_area",""),
            r.get("status","Pending"), r.get("stage_step",""), int(r.get("day_offset",0)),
            int(r.get("step_order",0)), r.get("scheduled_date",""), r.get("last_sent_at",""),
            r.get("notes",""), r.get("stage","Not Started"), now_ts))
    conn.commit()
    conn.close()


def load_schedule_df():
    conn = db_conn()
    df = pd.read_sql_query("SELECT * FROM schedule ORDER BY id ASC", conn)
    conn.close()
    return df


def bulk_update_status_by_email(selected_email, new_status, note):
    conn = db_conn()
    conn.execute("""UPDATE schedule SET status=?,
        stage = CASE WHEN ? IN ('Replied','Call Booked','Closed') THEN ? ELSE stage END,
        notes = CASE WHEN ? != '' THEN ? ELSE notes END
        WHERE email=? AND status IN ('Pending','Sent')""",
        (new_status, new_status, new_status, note, note, selected_email))
    conn.commit()
    conn.close()


def emergency_stop_active():
    return os.path.exists(EMERGENCY_STOP_FILE)


def set_emergency_stop(active: bool):
    if active:
        with open(EMERGENCY_STOP_FILE, "w") as f:
            f.write(datetime.now().isoformat(timespec="seconds"))
    else:
        if os.path.exists(EMERGENCY_STOP_FILE):
            os.remove(EMERGENCY_STOP_FILE)


def stop_all_pending_mails():
    conn = db_conn()
    conn.execute("UPDATE schedule SET status='Closed', notes='Emergency stop activated' WHERE status='Pending'")
    conn.commit()
    conn.close()
    set_emergency_stop(True)


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


def get_template_keys(segment, step):
    if step == "initial":
        if str(segment).strip().lower() == "founder":
            return "initial_founder_subject", "initial_founder_body"
        return "initial_poc_subject", "initial_poc_body"
    return f"{step}_subject", f"{step}_body"


def create_schedule_rows(base_date, lead_row, offsets, start_step="initial"):
    rows = []
    start_index = STEP_ORDER.index(start_step)
    for i, step in enumerate(STEP_ORDER[start_index:], start=start_index):
        day_offset = int(offsets.get(step, DEFAULT_OFFSETS[step]))
        rows.append({
            "company": str(lead_row.get("company","")).strip(),
            "first_name": str(lead_row.get("first_name","")).strip(),
            "email": str(lead_row.get("email","")).strip(),
            "role": str(lead_row.get("role","")).strip(),
            "segment": str(lead_row.get("segment","POC")).strip(),
            "owner": str(lead_row.get("owner","")).strip(),
            "problem_area": str(lead_row.get("problem_area","")).strip(),
            "status": "Pending", "stage_step": step, "day_offset": day_offset, "step_order": i,
            "scheduled_date": (base_date + timedelta(days=day_offset)).date().isoformat(),
            "last_sent_at": "", "notes": "", "stage": "Not Started"
        })
    return rows


init_db()
settings = get_settings()
templates = get_templates()

st.set_page_config(page_title="E-Cell Outreach OS", layout="wide")
st.title(APP_TITLE)

if emergency_stop_active():
    st.error("EMERGENCY STOP IS ACTIVE. worker.py will not send any mail until you clear it below.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1) Upload Leads", "2) Settings & Templates", "3) Preview / Monitor", "4) Replies / Stop", "5) Export"
])

with tab1:
    st.subheader("Upload leads CSVs")
    st.markdown("Required columns: company, first_name, email, role, segment, owner, problem_area")
    csv_files = st.file_uploader("Upload CSVs", type=["csv"], accept_multiple_files=True)
    start_date = st.date_input("Campaign start date", value=datetime.now().date())
    start_step = st.selectbox("Start from step", STEP_ORDER, index=0)

    c1, c2, c3, c4, c5 = st.columns(5)
    offsets = {
        "initial": c1.number_input("Initial day", min_value=0, value=DEFAULT_OFFSETS["initial"], step=1),
        "f1": c2.number_input("F1 day", min_value=0, value=DEFAULT_OFFSETS["f1"], step=1),
        "f2": c3.number_input("F2 day", min_value=0, value=DEFAULT_OFFSETS["f2"], step=1),
        "f3": c4.number_input("F3 day", min_value=0, value=DEFAULT_OFFSETS["f3"], step=1),
        "f4": c5.number_input("F4 day", min_value=0, value=DEFAULT_OFFSETS["f4"], step=1),
    }
    replace_mode = st.checkbox("Replace existing schedule", value=True)

    if st.button("Generate Follow-up Schedule"):
        if not csv_files:
            st.error("Please upload at least one CSV first.")
        else:
            all_rows, lead_count = [], 0
            for csv_file in csv_files:
                leads = pd.read_csv(csv_file).fillna("")
                lead_count += len(leads)
                for _, row in leads.iterrows():
                    all_rows.extend(create_schedule_rows(
                        datetime.combine(start_date, datetime.min.time()), row, offsets, start_step))
            if replace_mode:
                clear_schedule()
            insert_schedule_rows(all_rows)
            st.success(f"Generated {len(all_rows)} rows for {lead_count} leads. worker.py will pick these up automatically.")
            st.dataframe(load_schedule_df().head(30), use_container_width=True)

with tab2:
    st.subheader("Sender & signature")
    sender_name = st.text_input("Sender name", value=settings["sender_name"])
    sender_phone = st.text_input("Sender phone", value=settings["sender_phone"])
    gmail_user = st.text_input("Gmail address", value=settings["gmail_user"])
    gmail_app_password = st.text_input("Gmail App Password", value=settings["gmail_app_password"], type="password")

    if st.button("Save sender settings"):
        update_settings(sender_name, sender_phone, gmail_user.strip(), gmail_app_password.strip())
        st.success("Saved. worker.py reads this fresh on every send, so signatures will never be blank.")
        st.rerun()

    st.divider()
    st.subheader("LP Report attachment")
    st.caption("Auto-attached to every INITIAL email by worker.py. Never attached to follow-ups.")
    if settings["lp_report_name"]:
        st.info(f"Current LP report on file: {settings['lp_report_name']}")
        if st.button("Remove current LP report"):
            remove_lp_report()
            st.success("Removed.")
            st.rerun()
    else:
        st.warning("No LP report uploaded yet. Initial emails will send without an attachment.")

    lp_file = st.file_uploader("Upload / replace LP report (PDF/PPT/PPTX)", type=["pdf","ppt","pptx"], key="lp_upload")
    if lp_file is not None and st.button("Save LP report"):
        save_lp_report(lp_file)
        st.success(f"Saved {lp_file.name}.")
        st.rerun()

    st.divider()
    st.subheader("Emergency stop")
    cstop, cclear = st.columns(2)
    if cstop.button("EMERGENCY STOP - Close all pending mails", type="primary"):
        stop_all_pending_mails()
        st.error("Emergency stop activated. worker.py will refuse to send until cleared.")
        st.rerun()
    if cclear.button("Clear emergency stop"):
        set_emergency_stop(False)
        st.success("Cleared. worker.py can send again.")
        st.rerun()

    st.divider()
    st.subheader("Templates")
    template_key = st.selectbox("Choose template", list(templates.keys()))
    edited = st.text_area("Template content", templates[template_key], height=300)
    if st.button("Save Template"):
        save_template(template_key, sanitize_template_text(edited))
        st.success(f"Saved template: {template_key}")
        st.rerun()
    st.caption("Placeholders: {{FirstName}}, {{Company}}, {{Role}}, {{ProblemArea}}, {{SenderName}}, {{SenderPhone}}")

with tab3:
    st.subheader("Preview (no sending happens here)")
    st.info("Actual sending is done by worker.py running in the background, so it keeps sending even if this page refreshes or your browser disconnects.")
    settings = get_settings()
    templates_now = get_templates()
    preview_date = st.date_input("Preview date", value=datetime.now().date(), key="preview_date")

    df = load_schedule_df()
    if df.empty:
        st.info("No schedule yet. Upload leads first.")
    else:
        due = df[(df["scheduled_date"] == preview_date.isoformat()) & (df["status"] == "Pending")].copy()
        blocked = set(df[df["status"].isin(STOP_STATUSES)]["email"].tolist())
        due = due[~due["email"].isin(blocked)]
        st.write(f"Due on {preview_date.isoformat()}: {len(due)} email(s) - worker.py will send these automatically.")
        st.dataframe(due[["id","company","first_name","email","segment","stage_step","scheduled_date"]],
                     use_container_width=True)

        if st.button("Preview rendered content"):
            logs = []
            for _, row in due.iterrows():
                subj_key, body_key = get_template_keys(row["segment"], row["stage_step"])
                subject = render_template(templates_now.get(subj_key,""), {
                    "FirstName": row["first_name"], "Company": row["company"],
                    "Role": row["role"], "ProblemArea": row["problem_area"],
                    "SenderName": settings["sender_name"], "SenderPhone": settings["sender_phone"]})
                use_attachment = row["stage_step"] == "initial" and settings["lp_report_path"]
                logs.append({"email": row["email"], "step": row["stage_step"], "subject": subject,
                             "attachment": settings["lp_report_name"] if use_attachment else "none"})
            st.dataframe(pd.DataFrame(logs), use_container_width=True)

    st.divider()
    st.subheader("Live send status (auto-refreshes)")
    status_df = load_schedule_df()
    if not status_df.empty:
        counts = status_df["status"].value_counts()
        st.write(counts.to_dict())
        st.dataframe(status_df[["id","company","email","stage_step","status","scheduled_date","last_sent_at","notes"]]
                     .sort_values("id", ascending=False).head(50), use_container_width=True)

with tab4:
    st.subheader("Mark replies / stop follow-ups")
    df = load_schedule_df()
    if df.empty:
        st.info("No data yet.")
    else:
        selected_email = st.selectbox("Select lead email", sorted(df["email"].dropna().unique().tolist()))
        lead_rows = df[df["email"] == selected_email].copy()
        st.dataframe(lead_rows[["id","company","first_name","email","stage_step","scheduled_date","status","stage","notes"]],
                     use_container_width=True)
        new_status = st.selectbox("Set status (stops all future follow-ups)",
                                   ["Replied","Call Booked","Closed","Pending"])
        note = st.text_input("Add note")
        if st.button("Update lead status"):
            bulk_update_status_by_email(selected_email, new_status, note.strip())
            st.success(f"Updated to {new_status} for {selected_email}.")

with tab5:
    st.subheader("Export")
    out = load_schedule_df()
    if out.empty:
        st.info("Nothing to export yet.")
    else:
        st.dataframe(out, use_container_width=True)
        st.download_button("Download outreach_schedule.csv", data=out.to_csv(index=False).encode("utf-8"),
                            file_name="outreach_schedule.csv", mime="text/csv")