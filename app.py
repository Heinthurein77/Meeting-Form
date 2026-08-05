"""
Internal Training Survey Form — ABC-MIB Group Co., Ltd.

Streamlit + Supabase (Auth + Postgres) production app.
Run: streamlit run app.py
"""

import base64
import io
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ABC-MIB Training Survey",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

COMPANY_NAME = st.secrets.get("app", {}).get("company_name", "ABC-MIB Group Co., Ltd.")

RATING_OPTIONS = ["4 - Excellent", "3 - Good", "2 - Average", "1 - Poor"]
RATING_QUESTIONS = [
    ("q1_enjoyable", "1. I enjoyed the training session."),
    ("q2_organized", "2. The training was well organized."),
    ("q3_satisfied", "3. Overall, I am satisfied with this training."),
    ("q4_improved_understanding", "4. This training improved my understanding of the subject."),
    ("q5_respect_ideas", "5. My ideas and opinions were respected during the session."),
    ("q6_presenter_rating", "6. How would you rate the presenter?"),
]
OPEN_QUESTIONS = [
    ("q7_understanding_notes", "7. What did you understand from this training?"),
    ("q8_interesting_thing", "8. What was the most interesting thing you learned?"),
    ("q9_knowledge_application", "9. How will you apply this knowledge in your work?"),
    ("q10_challenge_addressed", "10. What challenge (if any) did this training help address?"),
    ("q11_future_topics", "11. What topics would you like to see in future training?"),
]

CUSTOM_CSS = """
<style>
    .block-container {max-width: 700px; padding-top: 2rem; padding-bottom: 3rem;}
    .survey-header {text-align: center; margin-bottom: 1.5rem;}
    .survey-header h1 {font-size: 1.4rem; margin-bottom: 0.1rem;}
    .survey-header h3 {font-size: 1.05rem; color: #555; font-weight: 400; margin-top: 0;}
    div[data-testid="stForm"] {border: 1px solid #e6e6e6; border-radius: 12px; padding: 1.5rem;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
# IMPORTANT: do NOT wrap this in @st.cache_resource. Streamlit Community
# Cloud runs one Python process shared by every visitor; a cached client
# would carry a single shared auth session and leak one user's login into
# another user's browser tab. Each browser session gets its own client,
# stored in that session's st.session_state.
def _is_privileged_key(key: str) -> bool:
    """Detect a secret/service_role key, which bypasses RLS and must never
    be used in a public-facing app."""
    if key.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) == 3:  # legacy JWT-style key (anon / service_role)
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
            if '"role":"service_role"' in payload:
                return True
        except Exception:
            pass
    return False


def get_supabase() -> Client:
    if "sb_client" not in st.session_state:
        supabase_secrets = st.secrets.get("supabase", {})
        url = supabase_secrets.get("url")
        key = supabase_secrets.get("key")

        if not url or not key or "YOUR_SUPABASE" in url or "YOUR_SUPABASE" in key:
            st.error(
                "**Supabase credentials are not configured.**\n\n"
                "- On Streamlit Community Cloud: open **Manage app → Settings → Secrets** "
                "and paste your `[supabase]` url and key.\n"
                "- Running locally: fill in the real values in `.streamlit/secrets.toml`.\n\n"
                "See README.md section 4/6 for the exact format."
            )
            st.stop()

        if _is_privileged_key(key):
            st.error(
                "**The configured Supabase key is a secret/service_role key.** "
                "It bypasses Row Level Security, so using it here would let any "
                "visitor read or modify all data — never use it in a public app.\n\n"
                "In Supabase: **Project Settings → API Keys**, copy the "
                "**Publishable key** (`sb_publishable_...`) — or the legacy "
                "**anon public** key — and use that instead."
            )
            st.stop()

        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client


# ---------------------------------------------------------------------------
# Session / auth helpers
# ---------------------------------------------------------------------------
def init_session_state():
    defaults = {
        "auth_user": None,      # {"id", "email"}
        "profile": None,        # row from users_profile
        "form_nonce": 0,        # bumped to reset the survey form widgets
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def load_profile(sb: Client, user_id: str):
    resp = sb.table("users_profile").select("*").eq("id", user_id).single().execute()
    return resp.data


def sign_in(sb: Client, email: str, password: str):
    result = sb.auth.sign_in_with_password({"email": email, "password": password})
    st.session_state.auth_user = {"id": result.user.id, "email": result.user.email}
    st.session_state.profile = load_profile(sb, result.user.id)


def sign_up(sb: Client, email: str, password: str, full_name: str, department: str, position: str):
    result = sb.auth.sign_up({"email": email, "password": password})
    if result.user is None:
        raise RuntimeError("Sign-up did not return a user. Please try again.")

    # If email confirmation is required, there is no active session yet.
    if result.session is not None and result.user.id:
        sb.table("users_profile").update(
            {"full_name": full_name, "department": department, "position": position}
        ).eq("id", result.user.id).execute()
        st.session_state.auth_user = {"id": result.user.id, "email": result.user.email}
        st.session_state.profile = load_profile(sb, result.user.id)
        return True  # logged in immediately
    return False  # needs email confirmation


def sign_out(sb: Client):
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for k in ("auth_user", "profile", "sb_client"):
        st.session_state.pop(k, None)
    st.rerun()


# ---------------------------------------------------------------------------
# Auth screen
# ---------------------------------------------------------------------------
def render_auth_screen(sb: Client):
    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Internal Training Survey Form</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, signup_tab = st.tabs(["Log In", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log In", use_container_width=True, type="primary")
        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                try:
                    sign_in(sb, email, password)
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

    with signup_tab:
        with st.form("signup_form"):
            full_name = st.text_input("Full Name", key="signup_name")
            col1, col2 = st.columns(2)
            with col1:
                department = st.text_input("Department", key="signup_dept")
            with col2:
                position = st.text_input("Position", key="signup_position")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            password2 = st.text_input("Confirm Password", type="password", key="signup_password2")
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
        if submitted:
            if not all([full_name, email, password, password2]):
                st.error("Please fill in all required fields.")
            elif password != password2:
                st.error("Passwords do not match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    logged_in = sign_up(sb, email, password, full_name, department, position)
                    if logged_in:
                        st.rerun()
                    else:
                        st.success("Account created! Please check your email to confirm, then log in.")
                except Exception as e:
                    st.error(f"Sign-up failed: {e}")


# ---------------------------------------------------------------------------
# Survey form (trainee)
# ---------------------------------------------------------------------------
def render_survey_form(sb: Client):
    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Internal Training Survey Form</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.auth_user['email']}**")
        if st.button("Log Out", use_container_width=True):
            sign_out(sb)

    tab_new, tab_mine = st.tabs(["📝 New Survey", "🗂️ My Submissions"])
    with tab_new:
        render_new_survey_tab(sb)
    with tab_mine:
        render_my_submissions_tab(sb)


def render_new_survey_tab(sb: Client):
    profile = st.session_state.profile or {}
    nonce = st.session_state.form_nonce

    with st.form(f"survey_form_{nonce}", clear_on_submit=False):
        st.subheader("Basic Information")

        trainee_name = st.text_input(
            "Trainee Name *", value=profile.get("full_name") or "", key=f"name_{nonce}"
        )
        c1, c2 = st.columns(2)
        with c1:
            position = st.text_input("Position", value=profile.get("position") or "", key=f"pos_{nonce}")
        with c2:
            department = st.text_input(
                "Department", value=profile.get("department") or "", key=f"dept_{nonce}"
            )

        training_course = st.text_input("Training Course *", key=f"course_{nonce}")
        presenter_name = st.text_input("Presenter Name", key=f"presenter_{nonce}")

        c3, c4 = st.columns(2)
        with c3:
            start_date = st.date_input("Start Date", value=date.today(), key=f"start_{nonce}")
        with c4:
            completed_date = st.date_input("Completed Date", value=date.today(), key=f"completed_{nonce}")

        c5, c6 = st.columns(2)
        with c5:
            training_hours = st.number_input(
                "Training Hours", min_value=0.0, step=0.5, key=f"hours_{nonce}"
            )
        with c6:
            time_range = st.text_input("Time Range (e.g. 09:00-12:00)", key=f"time_{nonce}")

        st.divider()
        st.subheader("Please rate the following")
        st.caption("4 = Excellent · 3 = Good · 2 = Average · 1 = Poor")

        rating_values = {}
        for field, label in RATING_QUESTIONS:
            st.markdown(f"**{label}** *")
            rating_values[field] = st.segmented_control(
                label, options=RATING_OPTIONS, key=f"{field}_{nonce}", label_visibility="collapsed"
            )

        st.divider()
        st.subheader("Your Feedback")

        open_values = {}
        for field, label in OPEN_QUESTIONS:
            open_values[field] = st.text_area(label, key=f"{field}_{nonce}", height=80)

        submitted = st.form_submit_button("Submit Survey", use_container_width=True, type="primary")

    if not submitted:
        return

    # ---- validation ----
    missing = []
    if not trainee_name.strip():
        missing.append("Trainee Name")
    if not training_course.strip():
        missing.append("Training Course")
    for field, label in RATING_QUESTIONS:
        if rating_values[field] is None:
            missing.append(label)

    if missing:
        st.error("Please complete the following required fields:\n\n- " + "\n- ".join(missing))
        return

    def rating_to_int(selected: str) -> int:
        return int(selected.split(" - ")[0])

    payload = {
        "user_id": st.session_state.auth_user["id"],
        "trainee_name": trainee_name.strip(),
        "position": position.strip(),
        "department": department.strip(),
        "training_course": training_course.strip(),
        "start_date": start_date.isoformat(),
        "completed_date": completed_date.isoformat(),
        "training_hours": training_hours,
        "time_range": time_range.strip(),
        "presenter_name": presenter_name.strip(),
        **{field: rating_to_int(rating_values[field]) for field, _ in RATING_QUESTIONS},
        **{field: open_values[field].strip() for field, _ in OPEN_QUESTIONS},
    }

    try:
        sb.table("survey_responses").insert(payload).execute()
        st.toast("Survey submitted — thank you!", icon="✅")
        st.session_state.form_nonce += 1  # forces a clean form on rerun
        st.rerun()
    except Exception as e:
        st.error(f"Could not submit survey: {e}")


def render_my_submissions_tab(sb: Client):
    """Lets a trainee see the surveys they personally submitted, with dates.
    RLS (responses_select_own) already restricts this query to their own
    rows even without the explicit filter, but we filter anyway for clarity.
    """
    user_id = st.session_state.auth_user["id"]

    if st.button("Refresh", key="refresh_my_submissions"):
        st.rerun()

    try:
        resp = (
            sb.table("survey_responses")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        st.error(f"Could not load your submissions: {e}")
        return

    rows = resp.data or []
    if not rows:
        st.info("You haven't submitted any surveys yet.")
        return

    st.caption(f"{len(rows)} submission(s)")

    for row in rows:
        created = pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d %H:%M")
        with st.expander(f"{created} — {row.get('training_course') or '(no course)'}"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Presenter:** {row.get('presenter_name') or '-'}")
                st.write(f"**Department:** {row.get('department') or '-'}")
            with c2:
                st.write(f"**Position:** {row.get('position') or '-'}")
                st.write(f"**Training Hours:** {row.get('training_hours') or '-'}")

            st.markdown("**Ratings**")
            for field, label in RATING_QUESTIONS:
                val = row.get(field)
                st.write(f"- {label} → **{val if val is not None else '-'}**/4")

            open_answers = [(label, row.get(field)) for field, label in OPEN_QUESTIONS if row.get(field)]
            if open_answers:
                st.markdown("**Feedback**")
                for label, val in open_answers:
                    st.write(f"- {label}")
                    st.write(val)


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------
QUESTION_LABELS = {
    "q1_enjoyable": "Q1 Enjoyable",
    "q2_organized": "Q2 Organized",
    "q3_satisfied": "Q3 Satisfied",
    "q4_improved_understanding": "Q4 Understanding",
    "q5_respect_ideas": "Q5 Respect Ideas",
    "q6_presenter_rating": "Q6 Presenter",
}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_responses(_sb: Client, cache_key: str) -> pd.DataFrame:
    resp = _sb.table("survey_responses").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(resp.data)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    df = df.copy()
    # Excel/openpyxl cannot store timezone-aware datetimes; Supabase returns
    # created_at with a UTC offset, so strip the tz before writing.
    for col in df.columns:
        if isinstance(df[col].dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_localize(None)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Responses")
    return output.getvalue()


def render_admin_dashboard(sb: Client):
    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Admin Analytics Dashboard</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.auth_user['email']}** (admin)")
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if st.button("Log Out", use_container_width=True):
            sign_out(sb)

    tab_analytics, tab_browse, tab_users = st.tabs(
        ["📊 Analytics", "📄 Browse Submissions", "🗂️ Manage Users"]
    )
    with tab_analytics:
        render_analytics_tab(sb)
    with tab_browse:
        render_browse_submissions_tab(sb)
    with tab_users:
        render_manage_users_tab(sb)


def render_analytics_tab(sb: Client):
    try:
        df = fetch_responses(sb, st.session_state.auth_user["id"])
    except Exception as e:
        st.error(f"Could not load responses: {e}")
        return

    if df.empty:
        st.info("No survey responses yet.")
        return

    # ---- Filters ----
    st.subheader("Filters")
    f1, f2, f3 = st.columns(3)
    with f1:
        courses = sorted(df["training_course"].dropna().unique().tolist())
        selected_courses = st.multiselect("Training Course", courses)
    with f2:
        departments = sorted(df["department"].dropna().unique().tolist())
        selected_departments = st.multiselect("Department", departments)
    with f3:
        min_date = df["created_at"].min().date()
        max_date = df["created_at"].max().date()
        date_range = st.date_input(
            "Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date
        )

    filtered = df.copy()
    if selected_courses:
        filtered = filtered[filtered["training_course"].isin(selected_courses)]
    if selected_departments:
        filtered = filtered[filtered["department"].isin(selected_departments)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
        filtered = filtered[
            (filtered["created_at"].dt.date >= start_d) & (filtered["created_at"].dt.date <= end_d)
        ]

    if filtered.empty:
        st.warning("No responses match the selected filters.")
        return

    rating_cols = list(QUESTION_LABELS.keys())
    filtered["overall_avg"] = filtered[rating_cols].mean(axis=1)

    # ---- Overview metrics ----
    st.subheader("Overview")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Submissions", len(filtered))
    m2.metric("Avg Overall Rating", f"{filtered['overall_avg'].mean():.2f} / 4")
    m3.metric("Courses Covered", filtered["training_course"].nunique())

    top_presenter_df = (
        filtered.dropna(subset=["presenter_name"])
        .groupby("presenter_name")["q6_presenter_rating"]
        .mean()
        .sort_values(ascending=False)
    )
    top_presenter = top_presenter_df.index[0] if not top_presenter_df.empty else "N/A"
    m4.metric("Top Rated Presenter", top_presenter)

    # ---- Average rating per course ----
    st.subheader("Average Rating by Course")
    course_avg = (
        filtered.groupby("training_course")["overall_avg"].mean().sort_values(ascending=False).round(2)
    )
    st.bar_chart(course_avg)

    # ---- Criteria ratings Q1-Q6 ----
    st.subheader("Average Rating by Criteria (Q1–Q6)")
    criteria_avg = filtered[rating_cols].mean().round(2)
    criteria_avg.index = [QUESTION_LABELS[c] for c in criteria_avg.index]
    st.bar_chart(criteria_avg)

    # ---- Top presenters table ----
    st.subheader("Top Rated Presenters")
    st.dataframe(
        top_presenter_df.round(2).reset_index().rename(
            columns={"presenter_name": "Presenter", "q6_presenter_rating": "Avg Rating"}
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ---- Data table ----
    st.subheader("All Submissions")
    display_cols = [
        "created_at", "trainee_name", "department", "training_course", "presenter_name",
        "overall_avg",
    ] + rating_cols + [f for f, _ in OPEN_QUESTIONS]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

    # ---- Export ----
    st.subheader("Export")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "Download CSV",
            data=filtered[display_cols].to_csv(index=False).encode("utf-8"),
            file_name=f"survey_responses_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with e2:
        st.download_button(
            "Download Excel (.xlsx)",
            data=to_excel_bytes(filtered[display_cols]),
            file_name=f"survey_responses_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Admin: browse submissions one-by-one (mirrors the trainee's own form view)
# ---------------------------------------------------------------------------
RATING_LABELS = {4: "Excellent", 3: "Good", 2: "Average", 1: "Poor"}


def render_browse_submissions_tab(sb: Client):
    try:
        df = fetch_responses(sb, st.session_state.auth_user["id"])
    except Exception as e:
        st.error(f"Could not load responses: {e}")
        return

    if df.empty:
        st.info("No survey responses yet.")
        return

    df = df.reset_index(drop=True)
    n = len(df)

    if "browse_idx" not in st.session_state or st.session_state.browse_idx >= n:
        st.session_state.browse_idx = 0

    def _label(i: int) -> str:
        r = df.iloc[i]
        created = r["created_at"].strftime("%Y-%m-%d %H:%M")
        return f"{i + 1}/{n} — {_s(r.get('trainee_name')) or '(no name)'} — {created}"

    nav1, nav2, nav3 = st.columns([1, 3, 1])
    with nav1:
        if st.button("⬅ Prev", use_container_width=True, disabled=st.session_state.browse_idx == 0):
            st.session_state.browse_idx -= 1
            st.rerun()
    with nav2:
        st.selectbox(
            "Jump to submission",
            options=list(range(n)),
            format_func=_label,
            key="browse_idx",
            label_visibility="collapsed",
        )
    with nav3:
        if st.button("Next ➡", use_container_width=True, disabled=st.session_state.browse_idx >= n - 1):
            st.session_state.browse_idx += 1
            st.rerun()

    st.divider()
    row = df.iloc[st.session_state.browse_idx]

    st.markdown(f"### {_s(row.get('trainee_name')) or '(no name)'}")
    st.caption(f"Submitted {row['created_at'].strftime('%Y-%m-%d %H:%M')}")

    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Position:** {_s(row.get('position')) or '-'}")
        st.write(f"**Department:** {_s(row.get('department')) or '-'}")
        st.write(f"**Training Course:** {_s(row.get('training_course')) or '-'}")
        st.write(f"**Presenter:** {_s(row.get('presenter_name')) or '-'}")
    with c2:
        st.write(f"**Start Date:** {_s(row.get('start_date')) or '-'}")
        st.write(f"**Completed Date:** {_s(row.get('completed_date')) or '-'}")
        st.write(f"**Training Hours:** {_s(row.get('training_hours')) or '-'}")
        st.write(f"**Time Range:** {_s(row.get('time_range')) or '-'}")

    st.divider()
    st.markdown("#### Ratings")
    for field, label in RATING_QUESTIONS:
        val = row.get(field)
        if pd.notna(val):
            val_int = int(val)
            text = f"{val_int} - {RATING_LABELS.get(val_int, '')}"
        else:
            text = "-"
        st.write(f"- {label} → **{text}**")

    st.divider()
    st.markdown("#### Feedback")
    for field, label in OPEN_QUESTIONS:
        val = _s(row.get(field))
        st.markdown(f"**{label}**")
        st.write(val if val else "_No response_")


# ---------------------------------------------------------------------------
# Admin: manage users
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_users(_sb: Client, cache_key: str) -> pd.DataFrame:
    resp = _sb.table("users_profile").select("*").order("email").execute()
    return pd.DataFrame(resp.data)


def _s(value) -> str:
    """Safely stringify a pandas row value, treating NaN/None as empty.
    pandas represents missing strings as float NaN, not None, so a plain
    `value or default` check isn't enough — NaN is truthy in Python."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def render_manage_users_tab(sb: Client):
    """Lets an admin view every user and promote/demote their role.
    Backed by the profile_update_admin RLS policy, which lets any admin
    update any users_profile row using the regular publishable key.
    """
    if st.button("Refresh Users", key="refresh_users"):
        st.cache_data.clear()
        st.rerun()

    try:
        users_df = fetch_users(sb, "manage_users")
    except Exception as e:
        st.error(f"Could not load users: {e}")
        return

    if users_df.empty:
        st.info("No users found.")
        return

    st.caption(f"{len(users_df)} user(s)")
    current_admin_id = st.session_state.auth_user["id"]

    for _, row in users_df.iterrows():
        uid = row["id"]
        current_role = _s(row.get("role")) or "user"
        is_self = uid == current_admin_id

        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.write(f"**{_s(row.get('full_name')) or '(no name)'}**")
                st.caption(_s(row.get("email")))
                extra = " · ".join(p for p in (_s(row.get("department")), _s(row.get("position"))) if p)
                if extra:
                    st.caption(extra)
            with c2:
                new_role = st.segmented_control(
                    "Role",
                    options=["user", "admin"],
                    default=current_role,
                    key=f"role_{uid}",
                    label_visibility="collapsed",
                    disabled=is_self,
                )
            with c3:
                if is_self:
                    st.caption("This is you")
                elif st.button("Save", key=f"save_{uid}", use_container_width=True):
                    if new_role == current_role:
                        st.info("No change.")
                    else:
                        try:
                            sb.table("users_profile").update({"role": new_role}).eq("id", uid).execute()
                            st.cache_data.clear()
                            st.toast(f"{_s(row.get('email'))} is now {new_role}", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not update role: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    init_session_state()
    sb = get_supabase()

    if st.session_state.auth_user is None:
        render_auth_screen(sb)
        return

    if st.session_state.profile is None:
        try:
            st.session_state.profile = load_profile(sb, st.session_state.auth_user["id"])
        except Exception as e:
            st.error(f"Could not load your profile: {e}")
            if st.button("Log Out"):
                sign_out(sb)
            return

    role = (st.session_state.profile or {}).get("role", "user")
    if role == "admin":
        render_admin_dashboard(sb)
    else:
        render_survey_form(sb)


if __name__ == "__main__":
    main()
